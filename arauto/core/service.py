"""Serviço de consulta — o núcleo compartilhado.

Todos os canais (terminais SC501, WebViewer, API) passam por aqui. Isso garante
que um código de balança, um rótulo de preço ou uma moeda padrão se comportem
igual, independente de quem perguntou.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Callable

from . import scalelabel
from .models import Product, display_price
from ..data.querylog import QueryLog
from ..data.repositories import ProductRepository, build_repository
from .settings import WEIGHT_FILE, Settings, get_settings

log = logging.getLogger("arauto.query")


def carregar_mascara(settings: Settings) -> scalelabel.Mascara:
    """Máscara vigente, migrando a configuração posicional antiga se existir.

    Instalações vindas do TC Server têm weightBarcodeSettings.config. Na
    primeira subida convertemos para máscara e gravamos em SCALE_MASK, para que
    a tela de configuração passe a ser a única fonte da verdade.
    """
    texto = settings.get("SCALE_MASK")
    legado = WEIGHT_FILE

    if not texto and legado.exists():
        valores = {}
        for linha in legado.read_text(encoding="utf-8").splitlines():
            if ";" in linha:
                chave, _, valor = linha.strip().partition(";")
                try:
                    valores[chave.strip().upper()] = int(valor.strip())
                except ValueError:
                    pass
        if valores:
            texto = scalelabel.da_config_antiga(
                valores.get("FIRST_DIGIT", 2), valores.get("INIT_BARCODE", 1),
                valores.get("END_BARCODE", 7), valores.get("INIT_WEIGHT", 7),
                valores.get("END_WEIGHT", 12),
            )
            settings.set("SCALE_MASK", texto)
            log.info("Configuração de balança antiga migrada para a máscara %s", texto)

    mascara = scalelabel.Mascara(texto or scalelabel.MASCARA_PADRAO)
    erros = mascara.validar()
    if erros:
        log.error("Máscara de balança inválida (%s): %s. Usando o padrão %s.",
                  mascara.texto, "; ".join(erros), scalelabel.MASCARA_PADRAO)
        mascara = scalelabel.Mascara(scalelabel.MASCARA_PADRAO)
    return mascara


@dataclass
class QueryResult:
    barcode: str
    found: bool
    description: str = ""
    price1: str = ""
    price2: str = ""
    label1: str = ""
    label2: str = ""
    label_not_found: str = ""
    by_weight: bool = False
    scale_type: str = ""
    weight: float | None = None
    unit_price1: str = ""
    unit_price2: str = ""
    db_barcode: str = ""
    elapsed_ms: float = 0.0

    def to_dict(self) -> dict:
        data = {
            "codigo_barras": self.barcode,
            "encontrado": self.found,
            "descricao": self.description,
            "preco1": self.price1,
            "preco2": self.price2,
            "rotulo1": self.label1,
            "rotulo2": self.label2,
            "tempo_ms": self.elapsed_ms,
        }
        if not self.found:
            data["mensagem"] = self.label_not_found
        if self.by_weight:
            data["etiqueta_balanca"] = {
                "tipo": self.scale_type,
                "peso": self.weight,
                "peso_estimado": self.scale_type == "total",
                "codigo_cadastro": self.db_barcode,
                "preco1_unitario": self.unit_price1,
                "preco2_unitario": self.unit_price2,
            }
            # nome antigo mantido para não quebrar integrações já em produção
            data["consulta_por_peso"] = data["etiqueta_balanca"]
        return data


@dataclass
class TerminalInfo:
    """Um terminal físico conectado ao servidor SC501."""

    address: str
    model: str = "desconhecido"
    tipo: int | None = None      # termType do SC504, usado pelo editor de layout
    connected_at: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    queries: int = 0
    last_barcode: str = ""

    def to_dict(self) -> dict:
        return {
            "endereco": self.address,
            "modelo": self.model,
            "tipo": self.tipo,
            "conectado_em": self.connected_at,
            "visto_em": self.last_seen,
            "consultas": self.queries,
            "ultimo_codigo": self.last_barcode,
        }


class QueryService:
    def __init__(self, settings: Settings | None = None,
                 repository: ProductRepository | None = None) -> None:
        self.settings = settings or get_settings()
        self.repo = repository or build_repository(self.settings)
        self.querylog = QueryLog(enabled=self.settings.get_bool("LOG_QUERIES", True))
        self.mascara = carregar_mascara(self.settings)
        self.started_at = time.time()
        self.terminals: dict[str, TerminalInfo] = {}
        self._subscribers: list[Callable[[QueryResult, str], None]] = []

    # ------------------------------------------------------------- consulta
    def query(self, barcode: str, *, origin: str = "", channel: str = "api") -> QueryResult:
        started = time.perf_counter()
        code = (barcode or "").strip()
        symbol = self.settings.currency_symbol
        result = QueryResult(
            barcode=code,
            found=False,
            label1=self.settings.get("LABEL1"),
            label2=self.settings.get("LABEL2"),
            label_not_found=self.settings.get("LABEL_NOT_FOUND"),
        )

        if not code:
            result.elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
            return result

        product = self.repo.get(code)

        # Não achou direto: pode ser etiqueta de balança.
        if product is None and self.settings.get_bool("SCALE_ENABLED", True):
            leitura = scalelabel.ler(code, self.mascara)
            if leitura is not None:
                base = self.buscar_candidatos(leitura.candidatos)
                if base is not None:
                    product = scalelabel.aplicar(base, leitura, symbol)
                    result.by_weight = True
                    result.scale_type = leitura.tipo
                    result.db_barcode = base.barcode
                    result.weight = float(product.weight) if product.weight else None
                    result.unit_price1 = display_price(base.price1, symbol)
                    result.unit_price2 = display_price(base.price2, symbol)
                    if leitura.dv_confere is False:
                        log.warning("Etiqueta %s com dígito verificador inconsistente", code)
                    log.info(
                        "Etiqueta de balança %s (%s) -> cadastro %s | preço final %s",
                        code, leitura.tipo, base.barcode, product.price1,
                    )

        if product is not None:
            result.found = True
            result.description = product.description or "Produto sem descrição"
            result.price1 = display_price(product.price1, symbol)
            result.price2 = display_price(product.price2, symbol)

        result.elapsed_ms = round((time.perf_counter() - started) * 1000, 2)

        self.querylog.record(
            origin=origin, channel=channel, barcode=code, found=result.found,
            description=result.description, price1=result.price1,
            price2=result.price2, elapsed_ms=result.elapsed_ms,
        )
        try:
            from ..plugins.manager import disparar_hooks_query
            disparar_hooks_query(result, origin, channel)
        except Exception:
            pass
        for callback in list(self._subscribers):
            try:
                callback(result, channel)
            except Exception:
                log.exception("Assinante de consulta falhou")
        return result

    def subscribe(self, callback: Callable[[QueryResult, str], None]) -> None:
        self._subscribers.append(callback)

    # ----------------------------------------------------------- terminais
    def terminal_connected(self, address: str) -> TerminalInfo:
        info = TerminalInfo(address=address)
        self.terminals[address] = info
        return info

    def terminal_disconnected(self, address: str) -> None:
        self.terminals.pop(address, None)

    # -------------------------------------------------------------- estado
    def status(self) -> dict:
        return {
            "aplicacao": "ArautoPY",
            "iniciado_em": self.started_at,
            "tempo_ativo_s": round(time.time() - self.started_at),
            "base": self.repo.status(),
            "terminais": [t.to_dict() for t in self.terminals.values()],
            "balanca": {
                "ativa": self.settings.get_bool("SCALE_ENABLED", True),
                **self.mascara.resumo(),
            },
            "exibicao": {
                "rotulo1": self.settings.get("LABEL1"),
                "rotulo2": self.settings.get("LABEL2"),
                "nao_encontrado": self.settings.get("LABEL_NOT_FOUND"),
                "moeda": self.settings.get("CURRENCY"),
                "simbolo": self.settings.currency_symbol,
                "loja": self.settings.store_name,
            },
        }

    def buscar_candidatos(self, candidatos: list[str]) -> Product | None:
        """Tenta as chaves em ordem: código puro, formato legado, sem zeros.

        A balança grava o código puro (`001110`), mas instalações vindas do TC
        Server têm o cadastro no formato antigo (`2001110000000`). Tentar as
        duas evita recadastro na migração.
        """
        for chave in candidatos:
            achado = self.repo.get(chave)
            if achado is not None:
                return achado
        return None

    def reload(self) -> int:
        self.mascara = carregar_mascara(self.settings)
        return self.repo.reload(force=True)

    def close(self) -> None:
        self.repo.close()
        self.querylog.close()


