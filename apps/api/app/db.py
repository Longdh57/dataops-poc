"""Ket noi Postgres. Mot cho duy nhat mo connection."""

from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row

from .settings import settings


@contextmanager
def db():
    with psycopg.connect(settings.database_url, row_factory=dict_row, connect_timeout=5) as conn:
        yield conn
