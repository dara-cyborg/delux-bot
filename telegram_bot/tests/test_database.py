import pytest

from telegram_bot.database import PostgresBackend


class DummyCursor:
    def __init__(self, row):
        self._row = row
        self.description = [("tenant_id",), ("created_at",), ("updated_at",), ("metadata",)]

    def execute(self, query, params=None):
        self.query = query
        self.params = params or ()

    def fetchone(self):
        return self._row

    def fetchall(self):
        return [self._row]


class DummyConnection:
    def __init__(self, row):
        self._row = row

    def cursor(self):
        return DummyCursor(self._row)


class DummyPsycopgModule:
    def connect(self, connection_string):
        return DummyConnection(("tenant-a", "2026-06-26T00:00:00", "2026-06-26T00:00:00", "{}"))


def test_postgres_backend_execute_one_converts_tuple_row(monkeypatch):
    dummy_module = DummyPsycopgModule()
    monkeypatch.setattr("telegram_bot.database.psycopg", dummy_module)
    backend = PostgresBackend("postgres://user:pass@localhost/db")

    result = backend.execute_one("SELECT * FROM tenants WHERE tenant_id = ?", ("tenant-a",))

    assert result == {
        "tenant_id": "tenant-a",
        "created_at": "2026-06-26T00:00:00",
        "updated_at": "2026-06-26T00:00:00",
        "metadata": "{}",
    }


def test_postgres_backend_execute_all_converts_tuple_rows(monkeypatch):
    dummy_module = DummyPsycopgModule()
    monkeypatch.setattr("telegram_bot.database.psycopg", dummy_module)
    backend = PostgresBackend("postgres://user:pass@localhost/db")

    result = backend.execute_all("SELECT * FROM tenants", ())

    assert result == [
        {
            "tenant_id": "tenant-a",
            "created_at": "2026-06-26T00:00:00",
            "updated_at": "2026-06-26T00:00:00",
            "metadata": "{}",
        }
    ]
