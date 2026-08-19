"""Registro da aplicação em memória.

O TC Server original guardava o log num banco H2 e mostrava numa janela Swing.
Aqui a mesma ideia, mas o consumidor é a tela `/logs`: um buffer circular que
segura as últimas linhas e um arquivo em disco para o histórico.

O buffer é circular de propósito. Um servidor de loja fica meses ligado; guardar
tudo em memória é vazamento garantido.
"""

from __future__ import annotations

import logging
import logging.handlers
import threading
from collections import deque
from datetime import datetime
from pathlib import Path

CAPACIDADE = 2000
ARQUIVO_LOG = "arauto.log"

NIVEIS = {
    "DEBUG": 10,
    "INFO": 20,
    "WARNING": 30,
    "ERROR": 40,
    "CRITICAL": 50,
}


class BufferHandler(logging.Handler):
    """Guarda as últimas linhas para a tela de logs ler."""

    def __init__(self, capacidade: int = CAPACIDADE) -> None:
        super().__init__()
        self._linhas: deque[dict] = deque(maxlen=capacidade)
        self._lock = threading.RLock()
        self._sequencia = 0

    def emit(self, record: logging.LogRecord) -> None:
        try:
            mensagem = record.getMessage()
        except Exception:
            mensagem = str(record.msg)
        if record.exc_info:
            mensagem += "\n" + self.format(record).split("\n", 1)[-1]

        with self._lock:
            self._sequencia += 1
            self._linhas.append({
                "id": self._sequencia,
                "ts": datetime.fromtimestamp(record.created).isoformat(timespec="milliseconds"),
                "nivel": record.levelname,
                "origem": record.name,
                "mensagem": mensagem,
            })

    def linhas(self, *, desde: int = 0, nivel_minimo: str = "DEBUG",
               origem: str = "", busca: str = "", limite: int = 300) -> list[dict]:
        piso = NIVEIS.get(nivel_minimo.upper(), 10)
        alvo = origem.strip().lower()
        termo = busca.strip().lower()

        with self._lock:
            candidatas = list(self._linhas)

        resultado = []
        for linha in candidatas:
            if linha["id"] <= desde:
                continue
            if NIVEIS.get(linha["nivel"], 0) < piso:
                continue
            if alvo and alvo not in linha["origem"].lower():
                continue
            if termo and termo not in linha["mensagem"].lower():
                continue
            resultado.append(linha)
        return resultado[-limite:]

    def origens(self) -> list[str]:
        with self._lock:
            return sorted({linha["origem"] for linha in self._linhas})

    def resumo(self) -> dict:
        with self._lock:
            linhas = list(self._linhas)
        contagem = {nivel: 0 for nivel in NIVEIS}
        for linha in linhas:
            if linha["nivel"] in contagem:
                contagem[linha["nivel"]] += 1
        return {
            "total_em_memoria": len(linhas),
            "capacidade": CAPACIDADE,
            "ultimo_id": linhas[-1]["id"] if linhas else 0,
            "por_nivel": contagem,
        }

    def limpar(self) -> None:
        with self._lock:
            self._linhas.clear()


BUFFER = BufferHandler()


def configurar(diretorio: Path, verboso: bool = False) -> None:
    """Liga console, arquivo rotativo e buffer de memória."""
    nivel = logging.DEBUG if verboso else logging.INFO
    formato = logging.Formatter(
        "%(asctime)s  %(levelname)-7s %(name)-20s %(message)s", datefmt="%H:%M:%S"
    )

    raiz = logging.getLogger()
    raiz.setLevel(nivel)
    for antigo in list(raiz.handlers):
        raiz.removeHandler(antigo)

    console = logging.StreamHandler()
    console.setFormatter(formato)
    raiz.addHandler(console)

    diretorio.mkdir(parents=True, exist_ok=True)
    arquivo = logging.handlers.RotatingFileHandler(
        diretorio / ARQUIVO_LOG, maxBytes=5_000_000, backupCount=5, encoding="utf-8"
    )
    arquivo.setFormatter(logging.Formatter(
        "%(asctime)s  %(levelname)-7s %(name)-20s %(message)s"
    ))
    raiz.addHandler(arquivo)

    BUFFER.setLevel(logging.DEBUG)  # o buffer guarda tudo; o filtro é na tela
    BUFFER.setFormatter(formato)
    raiz.addHandler(BUFFER)

    logging.getLogger("uvicorn.error").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def caminho_arquivo(diretorio: Path) -> Path:
    return diretorio / ARQUIVO_LOG


