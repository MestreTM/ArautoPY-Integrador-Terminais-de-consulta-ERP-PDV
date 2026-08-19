"""Registro das consultas.

Equivalente ao DbLogStream do original: cada consulta vira uma linha com
origem, código, se encontrou e o tempo de resposta. É isso que alimenta o
painel e o relatório de "produtos consultados e não encontrados", que na
prática é o dado mais útil que este servidor produz — cada não-encontrado é um
cadastro furado no ERP.
"""

from __future__ import annotations

import csv
import sqlite3
import threading
from datetime import datetime, timedelta
from pathlib import Path

from ..core.settings import EXPORT_DIR, LOG_DB


class QueryLog:
    def __init__(self, path: Path = LOG_DB, enabled: bool = True) -> None:
        self.enabled = enabled
        self._lock = threading.RLock()
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS queries (
                   id          INTEGER PRIMARY KEY AUTOINCREMENT,
                   ts          TEXT NOT NULL,
                   origin      TEXT NOT NULL DEFAULT '',
                   channel     TEXT NOT NULL DEFAULT '',
                   barcode     TEXT NOT NULL DEFAULT '',
                   found       INTEGER NOT NULL DEFAULT 0,
                   description TEXT NOT NULL DEFAULT '',
                   price1      TEXT NOT NULL DEFAULT '',
                   price2      TEXT NOT NULL DEFAULT '',
                   elapsed_ms  REAL NOT NULL DEFAULT 0
               )"""
        )
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_queries_ts ON queries(ts)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_queries_bc ON queries(barcode)")
        self._conn.commit()

    def record(self, *, origin: str, channel: str, barcode: str, found: bool,
               description: str = "", price1: str = "", price2: str = "",
               elapsed_ms: float = 0.0) -> None:
        if not self.enabled:
            return
        with self._lock:
            self._conn.execute(
                """INSERT INTO queries
                   (ts, origin, channel, barcode, found, description, price1, price2, elapsed_ms)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (datetime.now().isoformat(timespec="seconds"), origin, channel, barcode,
                 1 if found else 0, description, price1, price2, round(elapsed_ms, 2)),
            )
            self._conn.commit()

    def recent(self, limit: int = 50) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM queries ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def stats(self, days: int = 7) -> dict:
        since = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
        with self._lock:
            total, found = self._conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(found),0) FROM queries WHERE ts >= ?", (since,)
            ).fetchone()
            avg = self._conn.execute(
                "SELECT COALESCE(AVG(elapsed_ms),0) FROM queries WHERE ts >= ?", (since,)
            ).fetchone()[0]
            top = self._conn.execute(
                """SELECT barcode, description, COUNT(*) AS n FROM queries
                   WHERE ts >= ? AND found = 1
                   GROUP BY barcode ORDER BY n DESC LIMIT 10""",
                (since,),
            ).fetchall()
            missing = self._conn.execute(
                """SELECT barcode, COUNT(*) AS n, MAX(ts) AS ultima FROM queries
                   WHERE ts >= ? AND found = 0
                   GROUP BY barcode ORDER BY n DESC LIMIT 10""",
                (since,),
            ).fetchall()
            by_channel = self._conn.execute(
                """SELECT channel, COUNT(*) AS n FROM queries
                   WHERE ts >= ? GROUP BY channel ORDER BY n DESC""",
                (since,),
            ).fetchall()
        return {
            "periodo_dias": days,
            "total": total,
            "encontrados": found,
            "nao_encontrados": total - found,
            "taxa_acerto": round(found / total * 100, 1) if total else 0.0,
            "tempo_medio_ms": round(avg, 2),
            "mais_consultados": [dict(r) for r in top],
            "nao_encontrados_top": [dict(r) for r in missing],
            "por_canal": [dict(r) for r in by_channel],
        }

    def export_csv(self, day: str | None = None) -> Path:
        day = day or datetime.now().strftime("%Y-%m-%d")
        EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        target = EXPORT_DIR / f"consultas_{day}.csv"
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM queries WHERE DATE(ts) = ? ORDER BY id", (day,)
            ).fetchall()
        with target.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh, delimiter=";")
            writer.writerow(["data_hora", "origem", "canal", "codigo_barras",
                             "encontrado", "descricao", "preco1", "preco2", "ms"])
            for r in rows:
                writer.writerow([r["ts"], r["origin"], r["channel"], r["barcode"],
                                 "sim" if r["found"] else "nao", r["description"],
                                 r["price1"], r["price2"], r["elapsed_ms"]])
        return target

    def purge(self, older_than_days: int) -> int:
        cutoff = (datetime.now() - timedelta(days=older_than_days)).isoformat()
        with self._lock:
            cur = self._conn.execute("DELETE FROM queries WHERE ts < ?", (cutoff,))
            self._conn.commit()
            return cur.rowcount

    def close(self) -> None:
        with self._lock:
            self._conn.close()


