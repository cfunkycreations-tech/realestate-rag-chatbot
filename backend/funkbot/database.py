"""SQLAlchemy connection and Alembic migration helpers for the existing API.

The small SQL adapter preserves SQLite row/parameter behavior while endpoints
are incrementally moved to SQLAlchemy expressions. All connections are managed
by SQLAlchemy and closed after each transaction.
"""
from collections.abc import Mapping
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event
from sqlalchemy.engine import URL
from sqlalchemy.pool import NullPool


@lru_cache(maxsize=64)
def engine_for(path: str):
    engine = create_engine(URL.create('sqlite', database=path), connect_args={'timeout': 10}, poolclass=NullPool)

    @event.listens_for(engine, 'connect')
    def configure_sqlite(connection, _record):
        connection.execute('PRAGMA foreign_keys=ON')

    return engine


class Row(Mapping):
    def __init__(self, row): self.row = row
    def __getitem__(self, key): return self.row[key] if isinstance(key, int) else self.row._mapping[key]
    def __iter__(self): return iter(self.row._mapping)
    def __len__(self): return len(self.row._mapping)


class Result:
    def __init__(self, result): self.result = result
    @property
    def rowcount(self): return self.result.rowcount
    def fetchone(self):
        row = self.result.fetchone()
        return Row(row) if row is not None else None
    def fetchall(self): return [Row(row) for row in self.result.fetchall()]
    def __iter__(self): return (Row(row) for row in self.result)


class Connection:
    def __init__(self, connection): self.connection = connection
    def execute(self, statement, parameters=()):
        return Result(self.connection.exec_driver_sql(statement, parameters))
    def commit(self): self.connection.commit()


@contextmanager
def session(path: Path):
    with engine_for(str(path)).connect() as connection:
        try:
            yield Connection(connection)
            connection.commit()
        except BaseException:
            connection.rollback()
            raise


def migrate(path: Path):
    engine = engine_for(str(path))
    with engine.connect() as connection:
        connection.exec_driver_sql('PRAGMA journal_mode=WAL')
        connection.commit()
        config = Config()
        config.set_main_option('script_location', str(Path(__file__).parent / 'migrations'))
        config.attributes['connection'] = connection
        command.upgrade(config, 'head')
        connection.commit()
