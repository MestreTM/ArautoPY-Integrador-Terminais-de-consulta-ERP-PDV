"""Plugin: explorador de bancos de dados (SQLAlchemy / Firebird / SQLite / etc.).

Usa a URL configurada em DB_URL (modo EXTERNAL_SQL) ou uma URL informada
na própria tela. Permite listar tabelas, navegar registros, editar e excluir
(com confirmação dupla na exclusão).
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from fastapi import Body, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

log = logging.getLogger("arauto.plugin.explorador_banco")
_DIR = Path(__file__).resolve().parent

# Identificadores seguros (evita injeção em nomes de tabela/coluna)
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_$#]*$")


def _page() -> str:
    return (_DIR / "page.html").read_text(encoding="utf-8")


def _ident(nome: str, rotulo: str = "identificador") -> str:
    nome = (nome or "").strip()
    if not nome or not _IDENT.match(nome):
        raise ValueError(f"{rotulo} inválido: {nome!r}")
    return nome


def _url_efetiva(url: str | None) -> str:
    from arauto.core.settings import get_settings

    u = (url or "").strip()
    if u:
        return u
    return (get_settings().get("DB_URL") or "").strip()


def _engine(url: str):
    from arauto.data.repositories import _preparar_engine_sql

    return _preparar_engine_sql(url)


def _fechar(engine) -> None:
    from arauto.data.repositories import _fechar_engine

    _fechar_engine(engine)


def _is_firebird(url: str) -> bool:
    return "firebird" in (url or "").lower()


def _quote_ident(nome: str, firebird: bool) -> str:
    """Identificador seguro para SQL.

    No Firebird, nomes sem aspas são normalizados para MAIÚSCULAS. Aspas
    forçam o case literal e costumam gerar "Column unknown" quando o
    metadado veio em outro case (ex.: formulario vs FORMULARIO).
    """
    if firebird:
        return nome.upper()
    return nome


def _pk_firebird(conn, table: str) -> list[str]:
    from sqlalchemy import text as sql_text

    rows = conn.execute(
        sql_text(
            """
            SELECT TRIM(S.RDB$FIELD_NAME) AS COL
            FROM RDB$RELATION_CONSTRAINTS C
            JOIN RDB$INDEX_SEGMENTS S ON S.RDB$INDEX_NAME = C.RDB$INDEX_NAME
            WHERE C.RDB$CONSTRAINT_TYPE = 'PRIMARY KEY'
              AND UPPER(TRIM(C.RDB$RELATION_NAME)) = UPPER(:tab)
            ORDER BY S.RDB$FIELD_POSITION
            """
        ),
        {"tab": table},
    ).fetchall()
    return [str(r[0]).strip() for r in rows if r[0]]


def _colunas_firebird(conn, table: str) -> list[dict]:
    from sqlalchemy import text as sql_text

    rows = conn.execute(
        sql_text(
            """
            SELECT
                TRIM(RF.RDB$FIELD_NAME) AS NOME,
                F.RDB$FIELD_TYPE AS TIPO,
                RF.RDB$NULL_FLAG AS NOT_NULL
            FROM RDB$RELATION_FIELDS RF
            JOIN RDB$FIELDS F ON F.RDB$FIELD_NAME = RF.RDB$FIELD_SOURCE
            WHERE UPPER(TRIM(RF.RDB$RELATION_NAME)) = UPPER(:tab)
            ORDER BY RF.RDB$FIELD_POSITION
            """
        ),
        {"tab": table},
    ).fetchall()
    out = []
    for r in rows:
        out.append(
            {
                "nome": str(r[0]).strip(),
                "tipo": str(r[1]) if r[1] is not None else "",
                "nullable": r[2] is None,
            }
        )
    return out


def _info_tabela(url: str, table: str) -> dict:
    table = _ident(table, "tabela")
    engine = None
    try:
        from sqlalchemy import inspect, text as sql_text

        engine, url_n = _engine(url)
        fb = _is_firebird(url_n)
        conn = engine.connect()
        try:
            if fb:
                colunas = _colunas_firebird(conn, table)
                pks = _pk_firebird(conn, table)
                try:
                    total = int(
                        conn.execute(
                            sql_text(f"SELECT COUNT(*) FROM {_quote_ident(table, True)}")
                        ).scalar()
                        or 0
                    )
                except Exception:
                    total = None
            else:
                insp = inspect(engine)
                cols_raw = insp.get_columns(table)
                colunas = [
                    {
                        "nome": c["name"],
                        "tipo": str(c.get("type") or ""),
                        "nullable": bool(c.get("nullable", True)),
                    }
                    for c in cols_raw
                ]
                try:
                    pk = insp.get_pk_constraint(table) or {}
                    pks = list(pk.get("constrained_columns") or [])
                except Exception:
                    pks = []
                try:
                    total = int(
                        conn.execute(sql_text(f'SELECT COUNT(*) FROM "{table}"')).scalar()
                        or 0
                    )
                except Exception:
                    try:
                        total = int(
                            conn.execute(sql_text(f"SELECT COUNT(*) FROM {table}")).scalar()
                            or 0
                        )
                    except Exception:
                        total = None
        finally:
            try:
                conn.close()
            except Exception:
                pass
        return {
            "ok": True,
            "tabela": table,
            "colunas": colunas,
            "pk": pks,
            "total": total,
            "firebird": fb,
        }
    except Exception as exc:
        return {"ok": False, "detail": str(exc)}
    finally:
        _fechar(engine)


def _serializar(valor: Any) -> Any:
    if valor is None:
        return None
    if isinstance(valor, (bytes, memoryview)):
        try:
            return bytes(valor).decode("utf-8", errors="replace")
        except Exception:
            return f"<bytes {len(valor)}>"
    if isinstance(valor, (int, float, bool, str)):
        return valor
    return str(valor)


def _listar_linhas(
    url: str,
    table: str,
    *,
    limit: int = 50,
    offset: int = 0,
    filtro_col: str = "",
    filtro_val: str = "",
) -> dict:
    table = _ident(table, "tabela")
    limit = max(1, min(int(limit or 50), 500))
    offset = max(0, int(offset or 0))
    engine = None
    try:
        from sqlalchemy import text as sql_text

        engine, url_n = _engine(url)
        fb = _is_firebird(url_n)
        q_table = _quote_ident(table, fb)

        where = ""
        params: dict[str, Any] = {}
        if filtro_col and str(filtro_val) != "":
            col_ped = _ident(filtro_col, "coluna")
            col_real = col_ped
            try:
                info = _info_tabela(url, table)
                nomes = [c["nome"] for c in (info.get("colunas") or []) if c.get("nome")]
                mapa = {str(n).upper(): n for n in nomes}
                if col_ped.upper() in mapa:
                    col_real = mapa[col_ped.upper()]
                elif col_ped not in nomes:
                    return {
                        "ok": False,
                        "detail": (
                            f"Coluna '{filtro_col}' não existe em {table}. "
                            "Limpe o filtro ou escolha outra coluna."
                        ),
                    }
            except Exception:
                pass
            q_col = _quote_ident(col_real, fb)
            if fb:
                where = f" WHERE {q_col} CONTAINING :fval"
                params["fval"] = str(filtro_val)
            else:
                where = f" WHERE {q_col} LIKE :fval"
                params["fval"] = f"%{filtro_val}%"

        if fb:
            # FIRST/SKIP — sintaxe clássica Firebird
            sql = f"SELECT FIRST {limit} SKIP {offset} * FROM {q_table}{where}"
        else:
            sql = f"SELECT * FROM {q_table}{where} LIMIT {limit} OFFSET {offset}"

        conn = engine.connect()
        try:
            result = conn.execute(sql_text(sql), params)
            keys = list(result.keys())
            linhas = []
            for row in result.fetchall():
                m = row._mapping if hasattr(row, "_mapping") else dict(zip(keys, row))
                linhas.append({k: _serializar(m[k]) for k in keys})
            # total filtrado
            try:
                total = int(
                    conn.execute(
                        sql_text(f"SELECT COUNT(*) FROM {q_table}{where}"), params
                    ).scalar()
                    or 0
                )
            except Exception:
                total = len(linhas)
        finally:
            try:
                conn.close()
            except Exception:
                pass
        return {
            "ok": True,
            "tabela": table,
            "colunas": keys,
            "linhas": linhas,
            "limit": limit,
            "offset": offset,
            "total": total,
        }
    except Exception as exc:
        log.exception("listar linhas")
        return {"ok": False, "detail": str(exc)}
    finally:
        _fechar(engine)


def _where_pk(pk: list[str], pk_vals: dict, firebird: bool) -> tuple[str, dict]:
    if not pk:
        raise ValueError(
            "Tabela sem chave primária detectada. "
            "Edição/exclusão exige PK no banco."
        )
    partes = []
    params: dict[str, Any] = {}
    for i, col in enumerate(pk):
        c = _ident(col, "coluna PK")
        if c not in pk_vals and col not in pk_vals:
            raise ValueError(f"Falta valor da PK: {c}")
        val = pk_vals.get(c, pk_vals.get(col))
        key = f"pk{i}"
        partes.append(f"{_quote_ident(c, firebird)} = :{key}")
        params[key] = val
    return " AND ".join(partes), params


def _atualizar(url: str, table: str, pk_vals: dict, dados: dict) -> dict:
    table = _ident(table, "tabela")
    if not isinstance(dados, dict) or not dados:
        return {"ok": False, "detail": "Nenhum campo para atualizar."}
    engine = None
    try:
        from sqlalchemy import text as sql_text

        engine, url_n = _engine(url)
        fb = _is_firebird(url_n)
        info = _info_tabela(url, table)
        if not info.get("ok"):
            return info
        pk = info.get("pk") or []
        where, params = _where_pk(pk, pk_vals or {}, fb)
        sets = []
        for i, (col, val) in enumerate(dados.items()):
            c = _ident(str(col), "coluna")
            if c in pk:
                continue  # não altera PK
            key = f"v{i}"
            sets.append(f"{_quote_ident(c, fb)} = :{key}")
            params[key] = val
        if not sets:
            return {"ok": False, "detail": "Nenhuma coluna alterável."}
        sql = f"UPDATE {_quote_ident(table, fb)} SET {', '.join(sets)} WHERE {where}"
        conn = engine.connect()
        try:
            with conn.begin():
                r = conn.execute(sql_text(sql), params)
                afetados = r.rowcount if r.rowcount is not None else -1
        finally:
            try:
                conn.close()
            except Exception:
                pass
        return {"ok": True, "afetados": afetados, "detail": f"Atualizado ({afetados} linha(s))."}
    except Exception as exc:
        log.exception("atualizar")
        return {"ok": False, "detail": str(exc)}
    finally:
        _fechar(engine)


def _excluir(url: str, table: str, pk_vals: dict) -> dict:
    table = _ident(table, "tabela")
    engine = None
    try:
        from sqlalchemy import text as sql_text

        engine, url_n = _engine(url)
        fb = _is_firebird(url_n)
        info = _info_tabela(url, table)
        if not info.get("ok"):
            return info
        pk = info.get("pk") or []
        where, params = _where_pk(pk, pk_vals or {}, fb)
        sql = f"DELETE FROM {_quote_ident(table, fb)} WHERE {where}"
        conn = engine.connect()
        try:
            with conn.begin():
                r = conn.execute(sql_text(sql), params)
                afetados = r.rowcount if r.rowcount is not None else -1
        finally:
            try:
                conn.close()
            except Exception:
                pass
        return {"ok": True, "afetados": afetados, "detail": f"Excluído ({afetados} linha(s))."}
    except Exception as exc:
        log.exception("excluir")
        return {"ok": False, "detail": str(exc)}
    finally:
        _fechar(engine)


def setup(ctx):
    ctx.adicionar_aba("explorador-banco", "Explorador BD", "/plugins/explorador-banco/", ordem=35)

    @ctx.app.get("/plugins/explorador-banco/", response_class=HTMLResponse)
    def pagina(request: Request):
        scripts = '<script src="/plugins/explorador-banco/static/app.js"></script>'
        return ctx.render(
            request,
            titulo="Explorador de banco",
            conteudo=_page(),
            pagina="explorador-banco",
            scripts=scripts,
        )

    @ctx.app.get("/plugins/explorador-banco/static/app.js")
    def static_js():
        return FileResponse(_DIR / "app.js", media_type="application/javascript")

    @ctx.app.get("/plugins/explorador-banco/api/status")
    def api_status():
        from arauto.core.settings import get_settings

        s = get_settings()
        url = (s.get("DB_URL") or "").strip()
        modo = (s.get("DB_MODE") or "").upper()
        return {
            "ok": True,
            "modo": modo,
            "tem_url": bool(url),
            "url_mascara": _mascarar_url(url) if url else "",
            "external_sql": modo in ("EXTERNAL_SQL", "EXTERNAL_JDBC"),
        }

    @ctx.app.post("/plugins/explorador-banco/api/tabelas")
    def api_tabelas(corpo: dict = Body(default={})):
        from arauto.data.repositories import listar_tabelas_sql

        try:
            url = _url_efetiva((corpo or {}).get("url"))
        except Exception as exc:
            return JSONResponse({"ok": False, "detail": str(exc)}, status_code=400)
        if not url:
            return JSONResponse(
                {
                    "ok": False,
                    "detail": "Nenhuma URL. Configure DB_URL em Configuração ou informe uma URL aqui.",
                },
                status_code=400,
            )
        r = listar_tabelas_sql(url)
        if not r.get("ok"):
            return JSONResponse(r, status_code=400)
        return r

    @ctx.app.post("/plugins/explorador-banco/api/info")
    def api_info(corpo: dict = Body(...)):
        try:
            url = _url_efetiva(corpo.get("url"))
            table = corpo.get("tabela") or ""
        except Exception as exc:
            return JSONResponse({"ok": False, "detail": str(exc)}, status_code=400)
        if not url:
            return JSONResponse({"ok": False, "detail": "URL ausente."}, status_code=400)
        r = _info_tabela(url, table)
        if not r.get("ok"):
            return JSONResponse(r, status_code=400)
        return r

    @ctx.app.post("/plugins/explorador-banco/api/linhas")
    def api_linhas(corpo: dict = Body(...)):
        try:
            url = _url_efetiva(corpo.get("url"))
        except Exception as exc:
            return JSONResponse({"ok": False, "detail": str(exc)}, status_code=400)
        if not url:
            return JSONResponse({"ok": False, "detail": "URL ausente."}, status_code=400)
        r = _listar_linhas(
            url,
            corpo.get("tabela") or "",
            limit=int(corpo.get("limit") or 50),
            offset=int(corpo.get("offset") or 0),
            filtro_col=corpo.get("filtro_col") or "",
            filtro_val=corpo.get("filtro_val") or "",
        )
        if not r.get("ok"):
            return JSONResponse(r, status_code=400)
        return r

    @ctx.app.post("/plugins/explorador-banco/api/atualizar")
    def api_atualizar(corpo: dict = Body(...)):
        if not corpo.get("confirmar"):
            return JSONResponse(
                {"ok": False, "detail": "Confirmação obrigatória para editar."},
                status_code=400,
            )
        try:
            url = _url_efetiva(corpo.get("url"))
        except Exception as exc:
            return JSONResponse({"ok": False, "detail": str(exc)}, status_code=400)
        r = _atualizar(
            url,
            corpo.get("tabela") or "",
            corpo.get("pk") or {},
            corpo.get("dados") or {},
        )
        if not r.get("ok"):
            return JSONResponse(r, status_code=400)
        return r

    @ctx.app.post("/plugins/explorador-banco/api/excluir")
    def api_excluir(corpo: dict = Body(...)):
        """Exclusão exige confirmação dupla: confirmar=true e texto EXCLUIR."""
        if not corpo.get("confirmar"):
            return JSONResponse(
                {"ok": False, "detail": "Primeira confirmação ausente."},
                status_code=400,
            )
        token = str(corpo.get("confirmacao") or "").strip().upper()
        if token not in ("EXCLUIR", "DELETE"):
            return JSONResponse(
                {
                    "ok": False,
                    "detail": 'Digite EXCLUIR para confirmar a exclusão definitivamente.',
                },
                status_code=400,
            )
        try:
            url = _url_efetiva(corpo.get("url"))
        except Exception as exc:
            return JSONResponse({"ok": False, "detail": str(exc)}, status_code=400)
        r = _excluir(url, corpo.get("tabela") or "", corpo.get("pk") or {})
        if not r.get("ok"):
            return JSONResponse(r, status_code=400)
        return r


def _mascarar_url(url: str) -> str:
    """Oculta senha na URL para exibição."""
    try:
        if "://" not in url:
            return url
        esquema, resto = url.split("://", 1)
        if "@" in resto and ":" in resto.split("@", 1)[0]:
            cred, host = resto.split("@", 1)
            user = cred.split(":", 1)[0]
            return f"{esquema}://{user}:****@{host}"
        return url
    except Exception:
        return url


