"""Fontes de dados de produto.

Três modos, equivalentes aos do TC Server original:

  INTERNAL      base embarcada (SQLite aqui; H2 no original)
  EXTERNAL_TXT  arquivo `codigo|descricao|preco1|preco2|` em UTF-8
  EXTERNAL_SQL  banco externo via SQLAlchemy (equivalente ao JDBC)

Todos expõem a mesma interface e mantêm um índice em memória, porque o terminal
precisa de resposta em milissegundos e o volume típico (dezenas de milhares de
SKUs) cabe folgado na RAM.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
import time
from pathlib import Path

from ..core.models import Product
from ..core.settings import INTERNAL_DB, Settings

log = logging.getLogger("arauto.db")

TXT_DELIMITER = "|"
MAX_BARCODE = 20
MAX_DESCRIPTION = 200


class ProductRepository:
    """Interface comum. `read_only` controla o que a API expõe para escrita."""

    read_only = True
    mode = "UNKNOWN"

    def get(self, barcode: str) -> Product | None:
        raise NotImplementedError

    def search(self, query: str = "", limit: int = 50, offset: int = 0) -> list[Product]:
        raise NotImplementedError

    def count(self) -> int:
        raise NotImplementedError

    def reload(self, force: bool = False) -> int:
        return self.count()

    def save(self, product: Product) -> Product:
        raise PermissionError("Base de dados somente leitura")

    def delete(self, barcode: str) -> bool:
        raise PermissionError("Base de dados somente leitura")

    def status(self) -> dict:
        return {"modo": self.mode, "somente_leitura": self.read_only, "produtos": self.count()}

    def close(self) -> None:
        pass


class _MemoryIndexed(ProductRepository):
    """Base para repositórios que carregam tudo em memória e recarregam por timer."""

    def __init__(self, reload_interval_s: int = 600) -> None:
        self._map: dict[str, Product] = {}
        self._list: list[Product] = []
        self._lock = threading.RLock()
        self._last_load = 0.0
        self._interval = max(30, reload_interval_s)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start_autoreload(self) -> None:
        if self._thread is not None:
            return

        def loop() -> None:
            while not self._stop.wait(self._interval):
                try:
                    self.reload(force=True)
                except Exception:
                    log.exception("Falha ao recarregar a base")

        self._thread = threading.Thread(target=loop, name="db-reload", daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._stop.set()

    def _publish(self, products: list[Product]) -> None:
        mapping: dict[str, Product] = {}
        for p in products:
            if not p.barcode:
                continue
            if p.barcode in mapping:
                log.warning("Código duplicado (%s); a última linha prevalece", p.barcode)
            mapping[p.barcode] = p
        with self._lock:
            self._map = mapping
            self._list = list(mapping.values())
            self._last_load = time.time()

    def get(self, barcode: str) -> Product | None:
        with self._lock:
            return self._map.get((barcode or "").strip())

    def search(self, query: str = "", limit: int = 50, offset: int = 0) -> list[Product]:
        q = (query or "").strip().lower()
        with self._lock:
            source = self._list
            if q:
                source = [
                    p for p in source
                    if q in p.barcode.lower() or q in p.description.lower()
                ]
            return source[offset : offset + limit]

    def count(self) -> int:
        with self._lock:
            return len(self._map)

    def status(self) -> dict:
        data = super().status()
        data["ultima_carga"] = self._last_load
        data["intervalo_recarga_s"] = self._interval
        return data


# --------------------------------------------------------------------------- interno
class InternalRepository(ProductRepository):
    """Base embarcada em SQLite. Substitui o H2 do original."""

    read_only = False
    mode = "INTERNAL"

    def __init__(self, path: Path = INTERNAL_DB) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS products (
                   barcode     TEXT PRIMARY KEY,
                   description TEXT NOT NULL DEFAULT '',
                   price1      TEXT NOT NULL DEFAULT '',
                   price2      TEXT NOT NULL DEFAULT '',
                   updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
               )"""
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_products_desc ON products(description)"
        )
        self._conn.commit()

    def _row_to_product(self, row: sqlite3.Row) -> Product:
        return Product(
            barcode=row["barcode"],
            description=row["description"] or "",
            price1=row["price1"] or "",
            price2=row["price2"] or "",
        )

    def get(self, barcode: str) -> Product | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM products WHERE barcode = ?", ((barcode or "").strip(),)
            ).fetchone()
        return self._row_to_product(row) if row else None

    def search(self, query: str = "", limit: int = 50, offset: int = 0) -> list[Product]:
        q = (query or "").strip()
        with self._lock:
            if q:
                rows = self._conn.execute(
                    """SELECT * FROM products
                       WHERE barcode LIKE ? OR description LIKE ?
                       ORDER BY description LIMIT ? OFFSET ?""",
                    (f"%{q}%", f"%{q}%", limit, offset),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM products ORDER BY description LIMIT ? OFFSET ?",
                    (limit, offset),
                ).fetchall()
        return [self._row_to_product(r) for r in rows]

    def count(self) -> int:
        with self._lock:
            return self._conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]

    def save(self, product: Product) -> Product:
        barcode = (product.barcode or "").strip()
        if not barcode:
            raise ValueError("O código de barras não pode ser vazio")
        if len(barcode) > MAX_BARCODE:
            raise ValueError(f"Código de barras acima de {MAX_BARCODE} caracteres")
        with self._lock:
            self._conn.execute(
                """INSERT INTO products (barcode, description, price1, price2, updated_at)
                   VALUES (?,?,?,?, datetime('now'))
                   ON CONFLICT(barcode) DO UPDATE SET
                     description=excluded.description,
                     price1=excluded.price1,
                     price2=excluded.price2,
                     updated_at=datetime('now')""",
                (barcode, product.description or "", product.price1 or "", product.price2 or ""),
            )
            self._conn.commit()
        return product

    def delete(self, barcode: str) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM products WHERE barcode = ?", ((barcode or "").strip(),)
            )
            self._conn.commit()
            return cur.rowcount > 0

    def import_pipe_file(self, path: Path) -> int:
        """Carrega um arquivo no formato do TC Server para dentro da base interna."""
        products = _read_pipe_file(path)
        with self._lock:
            self._conn.executemany(
                """INSERT INTO products (barcode, description, price1, price2, updated_at)
                   VALUES (?,?,?,?, datetime('now'))
                   ON CONFLICT(barcode) DO UPDATE SET
                     description=excluded.description, price1=excluded.price1,
                     price2=excluded.price2, updated_at=datetime('now')""",
                [(p.barcode, p.description, p.price1, p.price2) for p in products],
            )
            self._conn.commit()
        return len(products)

    def close(self) -> None:
        with self._lock:
            self._conn.close()


# ------------------------------------------------------------------------ texto
def _read_pipe_file(path: Path) -> list[Product]:
    products: list[Product] = []
    text = path.read_text(encoding="utf-8", errors="replace")
    if text.startswith("\ufeff"):
        text = text[1:]
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        cols = line.split(TXT_DELIMITER)
        barcode = cols[0].strip() if cols else ""
        if not barcode:
            continue
        if len(barcode) > MAX_BARCODE:
            log.warning("Linha %d ignorada: código de barras longo demais", lineno)
            continue
        products.append(
            Product(
                barcode=barcode,
                description=(cols[1].strip() if len(cols) > 1 else "")[:MAX_DESCRIPTION],
                price1=cols[2].strip() if len(cols) > 2 else "",
                price2=cols[3].strip() if len(cols) > 3 else "",
            )
        )
    return products


class TextFileRepository(_MemoryIndexed):
    """Arquivo `codigo|descricao|preco1|preco2|`, recarregado por timer."""

    read_only = True
    mode = "EXTERNAL_TXT"

    def __init__(self, path: Path, reload_interval_min: int = 10) -> None:
        super().__init__(reload_interval_s=reload_interval_min * 60)
        self.path = Path(path)
        self._mtime = 0.0
        self.reload(force=True)
        self.start_autoreload()

    def reload(self, force: bool = False) -> int:
        if not self.path.exists():
            log.error("Arquivo de produtos não encontrado: %s", self.path)
            self._publish([])
            return 0
        mtime = self.path.stat().st_mtime
        if not force and mtime == self._mtime:
            return self.count()
        self._mtime = mtime
        products = _read_pipe_file(self.path)
        self._publish(products)
        log.info("Base de texto carregada: %d produtos de %s", len(products), self.path)
        return len(products)

    def status(self) -> dict:
        data = super().status()
        data["arquivo"] = str(self.path)
        data["arquivo_existe"] = self.path.exists()
        return data


# -------------------------------------------------------------------------- SQL
class SqlRepository(_MemoryIndexed):
    """Banco externo via SQLAlchemy. Equivale ao modo JDBC do original.

    Faz snapshot completo da tabela e reindexa em memória, que é o mesmo
    comportamento do TC Server (recarga horária, ou manual).
    """

    read_only = True
    mode = "EXTERNAL_SQL"

    def __init__(self, url: str, table: str, cols: dict[str, str],
                 reload_interval_min: int = 60) -> None:
        super().__init__(reload_interval_s=reload_interval_min * 60)
        try:
            from sqlalchemy import create_engine
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "O modo EXTERNAL_SQL exige SQLAlchemy. Instale com: pip install sqlalchemy"
            ) from exc

        url = (url or "").strip()
        # SQLAlchemy 2.x removeu o dialeto Firebird interno — use sqlalchemy-firebird.
        if url.lower().startswith("firebird"):
            try:
                import sqlalchemy_firebird  # noqa: F401
            except ImportError as exc:
                raise RuntimeError(
                    "Firebird exige o dialeto externo. Instale com: "
                    "pip install sqlalchemy sqlalchemy-firebird. "
                    "URL (Firebird 3+): "
                    "firebird+firebird://SYSDBA:masterkey@localhost/C:/produtos/dbvenda.fdb "
                    "— Firebird 2.5: pip install fdb e use firebird+fdb://..."
                ) from exc
            if url.lower().startswith("firebird://"):
                url = "firebird+firebird://" + url.split("://", 1)[1]

        self.url = url
        self.table = table
        self.cols = cols
        try:
            # pool_reset_on_return="rollback" reduz detach inválido no firebird-driver
            self._engine = create_engine(
                url,
                pool_pre_ping=True,
                pool_reset_on_return="rollback",
            )
        except Exception as exc:
            nome = type(exc).__name__
            if "firebird" in str(exc).lower() or nome == "NoSuchModuleError":
                raise RuntimeError(
                    f"Não foi possível carregar o dialeto do banco ({exc}). "
                    "Para Firebird no SQLAlchemy 2.x: "
                    "pip install sqlalchemy-firebird "
                    "e use URL firebird+firebird://USER:SENHA@HOST/caminho.fdb"
                ) from exc
            raise
        self._error: str | None = None
        self.reload(force=True)
        self.start_autoreload()

    def close(self) -> None:
        super().close()
        engine = getattr(self, "_engine", None)
        if engine is not None:
            try:
                engine.dispose()
            except Exception:
                log.debug("dispose do engine SQL ignorado", exc_info=True)
            self._engine = None


    def reload(self, force: bool = False) -> int:
        from sqlalchemy import text as sql_text

        select_cols = ", ".join(
            f"{self.cols[k]}" for k in ("barcode", "description", "price1", "price2")
            if self.cols.get(k)
        )
        query = f"SELECT {select_cols} FROM {self.table}"
        try:
            with self._engine.connect() as conn:
                rows = conn.execute(sql_text(query)).mappings().all()
            products = [Product.from_row(dict(r), self.cols) for r in rows]
            self._publish(products)
            self._error = None
            log.info("Base SQL carregada: %d produtos", len(products))
            return len(products)
        except Exception as exc:
            self._error = str(exc)
            log.error("Perda de conexão com o banco: %s", exc)
            return self.count()

    def status(self) -> dict:
        data = super().status()
        data["tabela"] = self.table
        data["erro"] = self._error
        return data





def _preparar_engine_sql(url: str):
    """Normaliza URL Firebird e devolve (engine, url_norm).

    Usa NullPool: conexões de teste/listagem não ficam no pool — evita o
    access violation do firebird-driver no ``Connection.__del__``.
    """
    url = (url or "").strip()
    if not url:
        raise RuntimeError("URL vazia.")
    try:
        from sqlalchemy import create_engine
        from sqlalchemy.pool import NullPool
    except ImportError as exc:
        raise RuntimeError("SQLAlchemy não instalado. pip install sqlalchemy") from exc

    if url.lower().startswith("firebird"):
        try:
            import sqlalchemy_firebird  # noqa: F401
        except ImportError as exc:
            raise RuntimeError(
                "Firebird exige sqlalchemy-firebird. pip install sqlalchemy-firebird"
            ) from exc
        if url.lower().startswith("firebird://"):
            url = "firebird+firebird://" + url.split("://", 1)[1]

    engine = create_engine(
        url,
        poolclass=NullPool,
        pool_pre_ping=True,
        pool_reset_on_return="rollback",
    )
    return engine, url


def _fechar_engine(engine) -> None:
    if engine is None:
        return
    try:
        engine.dispose()
    except Exception:
        log.debug("dispose ignorado", exc_info=True)


def listar_tabelas_sql(url: str) -> dict:
    """Lista tabelas de usuário do banco apontado pela URL."""
    try:
        from sqlalchemy import text as sql_text, inspect
    except ImportError:
        return {"ok": False, "detail": "SQLAlchemy não instalado."}

    engine = None
    try:
        engine, url_norm = _preparar_engine_sql(url)
        tabelas: list[str] = []
        conn = engine.connect()
        try:
            if "firebird" in url_norm.lower():
                rows = conn.execute(sql_text("""
                    SELECT TRIM(RDB$RELATION_NAME) AS T
                    FROM RDB$RELATIONS
                    WHERE RDB$SYSTEM_FLAG = 0 AND RDB$VIEW_BLR IS NULL
                    ORDER BY 1
                """)).fetchall()
                tabelas = [str(r[0]).strip() for r in rows if r[0]]
            else:
                insp = inspect(engine)
                tabelas = sorted(insp.get_table_names())
        finally:
            try:
                conn.close()
            except Exception:
                pass
        return {"ok": True, "tabelas": tabelas, "total": len(tabelas)}
    except RuntimeError as exc:
        return {"ok": False, "detail": str(exc)}
    except Exception as exc:
        return {"ok": False, "detail": str(exc)}
    finally:
        _fechar_engine(engine)


def listar_colunas_sql(url: str, table: str) -> dict:
    """Lista colunas de uma tabela."""
    table = (table or "").strip()
    if not table:
        return {"ok": False, "detail": "Informe o nome da tabela."}
    try:
        from sqlalchemy import text as sql_text, inspect
    except ImportError:
        return {"ok": False, "detail": "SQLAlchemy não instalado."}

    engine = None
    try:
        engine, url_norm = _preparar_engine_sql(url)
        colunas: list[str] = []
        conn = engine.connect()
        try:
            if "firebird" in url_norm.lower():
                rows = conn.execute(sql_text("""
                    SELECT TRIM(RF.RDB$FIELD_NAME) AS C
                    FROM RDB$RELATION_FIELDS RF
                    WHERE UPPER(TRIM(RF.RDB$RELATION_NAME)) = UPPER(:tab)
                    ORDER BY RF.RDB$FIELD_POSITION
                """), {"tab": table}).fetchall()
                colunas = [str(r[0]).strip() for r in rows if r[0]]
            else:
                insp = inspect(engine)
                colunas = [c["name"] for c in insp.get_columns(table)]
        finally:
            try:
                conn.close()
            except Exception:
                pass
        if not colunas:
            return {
                "ok": False,
                "detail": f"Tabela '{table}' sem colunas ou não encontrada.",
                "colunas": [],
            }
        return {"ok": True, "tabela": table, "colunas": colunas, "total": len(colunas)}
    except RuntimeError as exc:
        return {"ok": False, "detail": str(exc)}
    except Exception as exc:
        return {"ok": False, "detail": str(exc)}
    finally:
        _fechar_engine(engine)


def testar_conexao_sql(
    url: str,
    table: str = "",
    cols: dict[str, str] | None = None,
) -> dict:
    """Tenta conectar (e opcionalmente contar a tabela) sem gravar settings."""
    engine = None
    try:
        from sqlalchemy import text as sql_text
    except ImportError:
        return {"ok": False, "detail": "SQLAlchemy não instalado. pip install sqlalchemy"}

    try:
        engine, url_norm = _preparar_engine_sql(url)
    except RuntimeError as exc:
        return {"ok": False, "detail": str(exc)}

    try:
        conn = engine.connect()
        try:
            if "firebird" in url_norm.lower():
                conn.execute(sql_text("SELECT 1 FROM RDB$DATABASE"))
            else:
                conn.execute(sql_text("SELECT 1"))
            produtos = None
            if table:
                try:
                    total = conn.execute(sql_text(f"SELECT COUNT(*) FROM {table}")).scalar()
                    produtos = int(total or 0)
                except Exception as exc2:
                    return {
                        "ok": False,
                        "detail": (
                            f"Conectou, mas a tabela/consulta falhou: {exc2}. "
                            "Use «Mostrar tabelas» para escolher o nome certo."
                        ),
                        "conectou": True,
                    }
                if cols:
                    select_cols = ", ".join(
                        cols[k] for k in ("barcode", "description", "price1", "price2")
                        if cols.get(k)
                    )
                    if select_cols:
                        try:
                            conn.execute(sql_text(f"SELECT {select_cols} FROM {table}")).fetchone()
                        except Exception as exc3:
                            return {
                                "ok": False,
                                "detail": f"Conectou, mas as colunas falharam: {exc3}",
                                "conectou": True,
                                "produtos": produtos,
                            }
        finally:
            try:
                conn.close()
            except Exception:
                pass

        if produtos is not None:
            return {
                "ok": True,
                "conectou": True,
                "produtos": produtos,
                "detail": f"Conexão ok. Tabela {table}: {produtos} registro(s).",
            }
        return {"ok": True, "conectou": True, "detail": "Conexão bem-sucedida."}
    except Exception as exc:
        return {"ok": False, "detail": str(exc), "conectou": False}
    finally:
        _fechar_engine(engine)


# ------------------------------------------------------------------------ fábrica
def build_repository(settings: Settings) -> ProductRepository:
    mode = settings.get("DB_MODE").upper()
    if mode == "EXTERNAL_TXT":
        path = settings.get("PATH_FILE_PRODUCT")
        if not path:
            log.error("DB_MODE=EXTERNAL_TXT mas PATH_FILE_PRODUCT está vazio; usando base interna")
            return InternalRepository()
        return TextFileRepository(Path(path), settings.get_int("TXT_DB_RELOAD_INTERVAL_MIN", 10))
    if mode in ("EXTERNAL_SQL", "EXTERNAL_JDBC"):
        url = settings.get("DB_URL")
        if not url:
            log.error("DB_MODE=EXTERNAL_SQL mas DB_URL está vazio; usando base interna")
            return InternalRepository()
        return SqlRepository(
            url=url,
            table=settings.get("DB_PRODUCT_TABLE_NAME"),
            cols={
                "barcode": settings.get("DB_COL_BARCODE"),
                "description": settings.get("DB_COL_DESCRIPITION"),
                "price1": settings.get("DB_COL_PRICE1"),
                "price2": settings.get("DB_COL_PRICE2"),
            },
            reload_interval_min=settings.get_int("DB_RELOAD_INTERVAL_MIN", 60),
        )
    return InternalRepository()


