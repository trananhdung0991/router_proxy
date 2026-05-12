import os
import sqlite3
from contextlib import contextmanager
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union

Row = Dict[str, Any]
Params = Union[Tuple, List]

DEFAULT_DB_PATH = os.environ.get("ROUTER_PROXY_DB", "/etc/router_proxy.db")

class DB:
    """
    Generic SQLite utility with common SQL helpers.
    - Per-operation connections (safe for threads in Flask)
    - Dict-like rows (row_factory=sqlite3.Row)
    - Helpers: ensure_table, insert, upsert_row, update, delete, query_one/all, transaction
    """

    def __init__(self, path: str = DEFAULT_DB_PATH):
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        # initialize basic pragmas
        with self._connect() as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    def transaction(self):
        """
        Usage:
          with db.transaction() as cur:
              cur.execute("SQL ...", params)
        """
        conn = self._connect()
        try:
            cur = conn.cursor()
            yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # DDL
    def ensure_table(self, name: str, columns_sql: str) -> None:
        self.execute(f"CREATE TABLE IF NOT EXISTS {name} ({columns_sql})")

    # Basic exec/query
    def execute(self, sql: str, params: Params = ()) -> None:
        with self._connect() as conn:
            conn.execute(sql, params)
            conn.commit()

    def executemany(self, sql: str, seq_of_params: Iterable[Params]) -> None:
        with self._connect() as conn:
            conn.executemany(sql, seq_of_params)
            conn.commit()

    def query_all(self, sql: str, params: Params = ()) -> List[Row]:
        with self._connect() as conn:
            cur = conn.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]

    def query_one(self, sql: str, params: Params = ()) -> Optional[Row]:
        with self._connect() as conn:
            cur = conn.execute(sql, params)
            row = cur.fetchone()
            return dict(row) if row else None

    # Generic CRUD
    def insert(self, table: str, data: Dict[str, Any]) -> None:
        cols = ", ".join(data.keys())
        placeholders = ", ".join(["?"] * len(data))
        sql = f"INSERT INTO {table} ({cols}) VALUES ({placeholders})"
        self.execute(sql, tuple(data.values()))

    def upsert_row(self, table: str, pk: str, data: Dict[str, Any]) -> None:
        if pk not in data:
            raise ValueError(f"data must include primary key '{pk}'")
        cols = list(data.keys())
        col_list = ", ".join(cols)
        placeholders = ", ".join(["?"] * len(cols))
        update_list = ", ".join([f"{c}=excluded.{c}" for c in cols if c != pk]) or f"{pk}={pk}"
        sql = f"""
        INSERT INTO {table} ({col_list}) VALUES ({placeholders})
        ON CONFLICT({pk}) DO UPDATE SET {update_list}
        """
        self.execute(sql, tuple(data[c] for c in cols))

    def update(self, table: str, data: Dict[str, Any], where: str, params: Params = ()) -> None:
        set_clause = ", ".join([f"{k}=?" for k in data.keys()])
        sql = f"UPDATE {table} SET {set_clause} WHERE {where}"
        values = tuple(data.values())
        self.execute(sql, values + tuple(params))

    def delete(self, table: str, where: str, params: Params = ()) -> None:
        sql = f"DELETE FROM {table} WHERE {where}"
        self.execute(sql, params)

    def get_by_pk(self, table: str, pk: str, key: Any) -> Optional[Row]:
        return self.query_one(f"SELECT * FROM {table} WHERE {pk} = ?", (key,))

    def all_rows(self, table: str) -> List[Row]:
        return self.query_all(f"SELECT * FROM {table}")
