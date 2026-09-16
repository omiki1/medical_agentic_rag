"""Shared connection management; DAO classes own SQL and domain persistence."""

import sqlite3
from contextlib import contextmanager


class ResultRow(dict):
    def __getitem__(self, key):
        return list(self.values())[key] if isinstance(key, int) else super().__getitem__(key)


class QueryResult:
    def __init__(self, rows, rowcount=0, lastrowid=None):
        self.rows, self.rowcount, self.lastrowid = rows, rowcount, lastrowid
        self.position = 0

    def fetchone(self):
        if self.position >= len(self.rows):
            return None
        row = self.rows[self.position]
        self.position += 1
        return row

    def fetchall(self):
        rows = self.rows[self.position :]
        self.position = len(self.rows)
        return rows

    def __iter__(self):
        return iter(self.fetchall())


class DatabaseSession:
    def __init__(self, connection, dialect):
        self.connection, self.dialect = connection, dialect

    def execute(self, sql, parameters=()):
        if self.dialect in {"mysql", "postgres"}:
            sql = "START TRANSACTION" if sql == "BEGIN IMMEDIATE" else sql.replace("?", "%s")
        cursor = self.connection.cursor()
        try:
            cursor.execute(sql, parameters)
            rows = [ResultRow(dict(row)) for row in cursor.fetchall()] if cursor.description else []
            return QueryResult(rows, cursor.rowcount, getattr(cursor, "lastrowid", None))
        finally:
            cursor.close()

    def executescript(self, script):
        for statement in script.split(";"):
            if statement.strip():
                self.execute(statement)


class Database:
    def __init__(self, settings):
        self.settings = settings
        self.dialect = settings.database_backend
        settings.data_dir.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect(self):
        if self.dialect == "mysql":
            import pymysql

            connection = pymysql.connect(
                host=self.settings.mysql_host,
                port=self.settings.mysql_port,
                user=self.settings.mysql_user,
                password=self.settings.mysql_password,
                database=self.settings.mysql_database,
                charset="utf8mb4",
                autocommit=False,
                cursorclass=pymysql.cursors.DictCursor,
                connect_timeout=5,
                read_timeout=10,
                write_timeout=10,
            )
        elif self.dialect == "postgres":
            import psycopg
            from psycopg.rows import dict_row

            options = (
                {}
                if self.settings.postgres_dsn
                else dict(
                    host=self.settings.postgres_host,
                    port=self.settings.postgres_port,
                    user=self.settings.postgres_user,
                    password=self.settings.postgres_password,
                    dbname=self.settings.postgres_database,
                )
            )
            connection = psycopg.connect(
                self.settings.postgres_dsn, connect_timeout=5, row_factory=dict_row, **options
            )
        else:
            connection = sqlite3.connect(self.settings.data_dir / "sessions.sqlite", timeout=10)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys=ON")
        try:
            yield DatabaseSession(connection, self.dialect)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
