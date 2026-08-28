"""Configuração da aplicação.

Mantém compatibilidade de nomes de chave com o config.properties do TC Server
original, para que uma instalação existente possa ser migrada copiando o
arquivo. O formato é o mesmo: linhas `CHAVE=valor`, UTF-8.
"""

from __future__ import annotations

import os
import sys
import threading
from pathlib import Path
from typing import Any

APP_NAME = "ArautoPY"
APP_VERSION = "1.0.0"

# Nome anterior do projeto. Instalações existentes têm config, base de produtos
# e layouts aqui — o rename não pode custar o cadastro do cliente.
APP_DIR_LEGADO = Path.home() / ".tc-server-py"

# Mensagens geradas antes de o logging existir; run.py as imprime depois.
AVISOS_INICIALIZACAO: list[str] = []


def _migrar_dados_legados(antigo: Path, novo: Path) -> None:
    """Copia os dados da instalação antiga para o diretório novo.

    Copia em vez de mover de propósito: se algo der errado, ou se o operador
    precisar voltar para a versão anterior, os dados originais continuam lá.
    """
    import shutil

    try:
        shutil.copytree(antigo, novo)
    except Exception as exc:                     # noqa: BLE001
        AVISOS_INICIALIZACAO.append(
            f"Não consegui migrar os dados de {antigo} para {novo}: {exc}. "
            f"Copie a pasta manualmente, ou aponte ARAUTO_HOME para {antigo}."
        )
        return
    AVISOS_INICIALIZACAO.append(
        f"Dados migrados de {antigo} para {novo} (a pasta antiga foi mantida "
        f"como backup)."
    )


def _diretorio_dados() -> Path:
    # ARAUTO_HOME é o nome atual; TCSERVER_HOME continua aceito para não
    # quebrar scripts e serviços que já apontavam para lá.
    for variavel in ("ARAUTO_HOME", "TCSERVER_HOME"):
        valor = os.environ.get(variavel)
        if valor:
            return Path(valor)

    novo = Path.home() / ".arauto"
    if not novo.exists() and APP_DIR_LEGADO.exists():
        _migrar_dados_legados(APP_DIR_LEGADO, novo)
    return novo


APP_DIR = _diretorio_dados()


def resource_root() -> Path:
    """Raiz dos arquivos empacotados (PyInstaller) ou do código-fonte.

    Com ``--onefile``, o PyInstaller extrai templates/static em
    ``sys._MEIPASS``. Em desenvolvimento, aponta para o pacote ``arauto``.
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "arauto"
    return Path(__file__).resolve().parent.parent
CONFIG_FILE = APP_DIR / "config.properties"
WEIGHT_FILE = APP_DIR / "weightBarcodeSettings.config"  # legado, só para migração
INTERNAL_DB = APP_DIR / "products.sqlite3"
LOG_DB = APP_DIR / "querylog.sqlite3"
EXPORT_DIR = APP_DIR / "export"

DEFAULTS: dict[str, str] = {
    # --- servidores ---
    "AUTO_INIT_501": "true",
    "AUTO_INIT_504": "true",
    "AUTO_INIT_HTTP": "true",
    "LAST_PORT_501": "6500",
    "LAST_PORT_504": "16510",
    "SC504_FRAME": "B-H-I-LE",
    "SC504_PASSIVE": "false",
    "SC501_PASSIVE": "false",
    "PROTOCOL_DEBUG": "false",
    "PORT_WEBVIEWER": "6689",
    "PORT_API": "5589",
    "BIND_HOST": "0.0.0.0",
    "LOCAL_HOSTNAME": "arauto.localhost",
    "OPEN_BROWSER_ON_START": "true",
    # --- base de dados ---
    # INTERNAL | EXTERNAL_TXT | EXTERNAL_SQL
    "DB_MODE": "INTERNAL",
    "PATH_FILE_PRODUCT": "",
    "TXT_DB_RELOAD_INTERVAL_MIN": "1",
    "DB_URL": "",
    "DB_USER": "",
    "DB_PASSWORD": "",
    "DB_PRODUCT_TABLE_NAME": "PRODUCTS",
    "DB_COL_BARCODE": "BARCODE",
    "DB_COL_BARCODE_ALT": "",
    "DB_COL_DESCRIPITION": "DESCRIPTION",
    "DB_COL_PRICE1": "PRICE_1",
    "DB_COL_PRICE2": "PRICE_2",
    "DB_RELOAD_INTERVAL_MIN": "1",
    # --- etiqueta de balança ---
    "SCALE_MASK": "2CCCCCCTTTTTV",
    "SCALE_ENABLED": "true",
    # --- exibição ---
    "LABEL1": "Preço",
    "LABEL2": "Preço personalizado",
    "LABEL_NOT_FOUND": "Produto não encontrado",
    "CURRENCY": "BRL",
    "STORE_NAME": "",
    "IDLE_RESET_SECONDS": "12",
    # --- imagem do produto (SC504 / TC-506 Mídia) ---
    # Quando ativo e PRODUCT_IMAGE_URL preenchido, o servidor baixa a imagem
    # do produto e envia via IDvShowImg na consulta de preço.
    # Placeholders aceitos na URL: {barcode}, {codigo}, {gtin}
    # Padrão: CDN Bluesoft Cosmos (foto pública por GTIN/EAN).
    "SHOW_PRODUCT_IMAGE": "true",
    "PRODUCT_IMAGE_URL": "https://cdn-cosmos.bluesoft.com.br/products/{barcode}",
    "PRODUCT_IMAGE_PACK_URL": "",  # vazio = último prod_ean_imagens.zip nos releases do repo oficial
    # --- API ---
    "API_KEY": "",
    "API_CORS_ORIGINS": "*",
    # --- log ---
    "LOG_QUERIES": "true",
    "EXPORT_CSV_ENABLED": "false",
    "EXPORT_CSV_ERASE_DAYS": "90",
    "AUTOSTART_ENABLED": "false",
    "SETUP_COMPLETE": "",
    "ADMIN_USER": "",
    "ADMIN_PASSWORD_HASH": "",
    "SESSION_SECRET": "",
}

CURRENCY_SYMBOLS = {"BRL": "R$", "USD": "$", "EUR": "€", "NONE": ""}


class Settings:
    """Leitor/gravador de config no formato .properties."""

    _instance: "Settings | None" = None
    _lock = threading.Lock()

    def __init__(self, path: Path = CONFIG_FILE) -> None:
        self.path = path
        self._data: dict[str, str] = dict(DEFAULTS)
        self._mutex = threading.RLock()
        self.load()

    @classmethod
    def instance(cls) -> "Settings":
        with cls._lock:
            if cls._instance is None:
                cls._instance = Settings()
            return cls._instance

    # ------------------------------------------------------------------ io
    def load(self) -> None:
        APP_DIR.mkdir(parents=True, exist_ok=True)
        EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.save()
            return
        do_arquivo: set[str] = set()
        with self._mutex:
            for raw in self.path.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if not line or line.startswith(("#", "!")):
                    continue
                if "=" not in line:
                    continue
                key, _, value = line.partition("=")
                chave = key.strip()
                self._data[chave] = value.strip()
                do_arquivo.add(chave)
        # Instalação antiga: não reabre o assistente.
        if "SETUP_COMPLETE" not in do_arquivo:
            self.set("SETUP_COMPLETE", "true")
        if not (self.get("SESSION_SECRET") or "").strip():
            import secrets
            self.set("SESSION_SECRET", secrets.token_hex(32))

    def save(self) -> None:
        with self._mutex:
            APP_DIR.mkdir(parents=True, exist_ok=True)
            lines = [f"# {APP_NAME} {APP_VERSION}"]
            lines += [f"{k}={v}" for k, v in sorted(self._data.items())]
            self.path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # --------------------------------------------------------------- acesso
    def get(self, key: str, default: Any = None) -> str:
        with self._mutex:
            value = self._data.get(key)
        if value is None or value == "":
            if default is not None:
                return str(default)
            return DEFAULTS.get(key, "")
        return value

    def set(self, key: str, value: Any) -> None:
        with self._mutex:
            self._data[key] = "" if value is None else str(value)
        self.save()

    def get_int(self, key: str, default: int | None = None) -> int:
        try:
            return int(float(self.get(key)))
        except (TypeError, ValueError):
            return default if default is not None else int(DEFAULTS.get(key, 0))

    def get_bool(self, key: str, default: bool = False) -> bool:
        value = self.get(key).strip().lower()
        if value in ("true", "1", "yes", "sim", "on"):
            return True
        if value in ("false", "0", "no", "nao", "não", "off"):
            return False
        return default

    def as_dict(self) -> dict[str, str]:
        with self._mutex:
            return dict(self._data)

    # ------------------------------------------------------------- atalhos
    @property
    def currency_symbol(self) -> str:
        return CURRENCY_SYMBOLS.get(self.get("CURRENCY").upper(), "")

    @property
    def store_name(self) -> str:
        return self.get("STORE_NAME") or ""


def get_settings() -> Settings:
    return Settings.instance()


