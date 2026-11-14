"""Adopt existing slice-2 tables, or create them for a new installation.

All statements are additive. Existing rows, encrypted settings and identifiers
remain untouched, including for a slice-1 database that has not seen slice 2.
"""
from alembic import op

revision = '0001_adopt_slice2'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    statements = [
        'CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT NOT NULL)',
        'CREATE TABLE IF NOT EXISTS bots (id TEXT PRIMARY KEY, name TEXT NOT NULL, title TEXT NOT NULL, personality TEXT NOT NULL, color TEXT NOT NULL, shape TEXT NOT NULL, profile TEXT NOT NULL, created_at REAL NOT NULL)',
        'CREATE TABLE IF NOT EXISTS messages (id TEXT PRIMARY KEY, bot_id TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE, role TEXT NOT NULL, content TEXT NOT NULL, created_at REAL NOT NULL)',
        'CREATE TABLE IF NOT EXISTS usage (id INTEGER PRIMARY KEY, bot_id TEXT REFERENCES bots(id) ON DELETE SET NULL, gateway TEXT, model TEXT, prompt_tokens INTEGER, completion_tokens INTEGER, cost REAL, created_at REAL NOT NULL)',
        'CREATE TABLE IF NOT EXISTS login_guard (id INTEGER PRIMARY KEY CHECK (id=1), failures INTEGER NOT NULL DEFAULT 0, locked_until REAL NOT NULL DEFAULT 0)',
        'INSERT OR IGNORE INTO login_guard (id) VALUES (1)',
        'CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, bot_id TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE, status TEXT NOT NULL, created_at REAL NOT NULL, updated_at REAL NOT NULL)',
        "CREATE UNIQUE INDEX IF NOT EXISTS one_active_run_per_bot ON runs(bot_id) WHERE status IN ('queued', 'running', 'waiting_approval')",
        'CREATE TABLE IF NOT EXISTS run_events (id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE, event_type TEXT NOT NULL, payload TEXT NOT NULL, created_at REAL NOT NULL)',
        'CREATE INDEX IF NOT EXISTS run_events_order ON run_events(run_id, id)',
    ]
    for statement in statements:
        op.execute(statement)


def downgrade():
    raise RuntimeError('Funk Bot migrations are forward-only; restore a backup to downgrade.')
