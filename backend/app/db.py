"""Neon connection pool. Opened in app lifespan, not at import (keeps tests offline)."""
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from .config import settings

pool = ConnectionPool(
    settings.DATABASE_URL,
    min_size=1,
    max_size=settings.DB_POOL_MAX,
    open=False,
    timeout=15,                      # Neon may wake from scale-to-zero
    check=ConnectionPool.check_connection,
    kwargs={"row_factory": dict_row, "prepare_threshold": None},  # None: safe behind pgbouncer
)
