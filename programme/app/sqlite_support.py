"""Connections close deterministically after their transaction context exits."""
import sqlite3
import os


def postgres_enabled():
    backend = os.environ.get('ALIGN_DATABASE_BACKEND', 'sqlite').strip().lower()
    if backend not in ('sqlite', 'postgres'):
        raise RuntimeError('Unknown ALIGN_DATABASE_BACKEND; expected sqlite or postgres')
    return backend == 'postgres'


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()


def connect(path, **kwargs):
    if postgres_enabled():
        from postgres_support import connect as postgres_connect
        return postgres_connect(path)
    kwargs.setdefault('factory', ClosingConnection)
    connection = sqlite3.connect(path, **kwargs)
    try:
        connection.execute('PRAGMA foreign_keys=ON')
        connection.execute('PRAGMA journal_mode=WAL')
        connection.execute('PRAGMA busy_timeout=5000')
        return connection
    except Exception:
        connection.close()
        raise
