"""Routine suggestions discovered from repeated completed work."""
from alembic import op
revision='0026_learned_routines'
down_revision='0025_computer_permissions'
branch_labels=None
depends_on=None

def upgrade():
    op.execute('''CREATE TABLE routine_suggestions (
        id TEXT PRIMARY KEY, bot_id TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
        fingerprint TEXT NOT NULL, title TEXT NOT NULL, instructions TEXT NOT NULL,
        examples INTEGER NOT NULL, status TEXT NOT NULL CHECK(status IN ('pending','approved','dismissed')),
        created_at REAL NOT NULL, routine_id TEXT REFERENCES routines(id) ON DELETE SET NULL,
        UNIQUE(bot_id,fingerprint)
    )''')

def downgrade():
    raise RuntimeError('Funk Bot migrations are forward-only; restore a backup to downgrade.')
