"""Persist owner-initiated handoffs without modifying existing missions."""
from alembic import op
revision = '0016_handoffs'
down_revision = '0015_followups'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('''CREATE TABLE handoffs (
        id TEXT PRIMARY KEY,
        from_bot_id TEXT REFERENCES bots(id) ON DELETE SET NULL,
        to_bot_id TEXT REFERENCES bots(id) ON DELETE SET NULL,
        mission_id TEXT NOT NULL UNIQUE REFERENCES missions(id) ON DELETE CASCADE,
        reason TEXT NOT NULL,
        context TEXT NOT NULL,
        created_at REAL NOT NULL
    )''')
    op.execute('CREATE INDEX handoffs_sender ON handoffs(from_bot_id,created_at DESC,id)')
    op.execute('CREATE INDEX handoffs_receiver ON handoffs(to_bot_id,created_at DESC,id)')


def downgrade():
    raise RuntimeError('Funk Bot migrations are forward-only; restore a backup to downgrade.')
