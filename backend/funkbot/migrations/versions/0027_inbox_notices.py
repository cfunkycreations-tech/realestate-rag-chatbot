"""Persistent owner inbox notifications."""
from alembic import op
revision='0027_inbox_notices'
down_revision='0026_learned_routines'
branch_labels=None
depends_on=None

def upgrade():
    op.execute('''CREATE TABLE inbox_notices (
        id TEXT PRIMARY KEY, bot_id TEXT REFERENCES bots(id) ON DELETE SET NULL,
        kind TEXT NOT NULL, title TEXT NOT NULL, body TEXT NOT NULL,
        run_id TEXT, mission_id TEXT, created_at REAL NOT NULL, read_at REAL
    )''')
    op.execute('CREATE INDEX inbox_notices_recent ON inbox_notices(created_at DESC)')

def downgrade(): raise RuntimeError('Funk Bot migrations are forward-only; restore a backup to downgrade.')
