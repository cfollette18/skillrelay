"""SQLite persistence; each mutation is serialized and crash-safe."""
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self.connect() as db:
            db.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS records (
                kind TEXT NOT NULL, id TEXT NOT NULL, body TEXT NOT NULL,
                PRIMARY KEY(kind,id));
            CREATE TABLE IF NOT EXISTS audit (
                seq INTEGER PRIMARY KEY, at REAL NOT NULL, actor TEXT NOT NULL,
                action TEXT NOT NULL, body TEXT NOT NULL);
            PRAGMA user_version=1;
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def get(db, kind, key):
        row = db.execute("SELECT body FROM records WHERE kind=? AND id=?", (kind, key)).fetchone()
        if not row:
            raise ValueError(f"Unknown {kind}: {key}")
        return json.loads(row[0])

    @staticmethod
    def put(db, kind, key, value):
        db.execute("INSERT INTO records VALUES(?,?,?) ON CONFLICT(kind,id) DO UPDATE SET body=excluded.body",
                   (kind, key, encoded(value)))

    @staticmethod
    def all(db, kind):
        return [json.loads(r[0]) for r in db.execute(
            "SELECT body FROM records WHERE kind=? ORDER BY rowid", (kind,))]
