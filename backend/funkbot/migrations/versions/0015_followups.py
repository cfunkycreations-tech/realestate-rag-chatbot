"""Persist Bot follow-ups without changing existing conversations or runs."""
from alembic import op
revision = '0015_followups'
down_revision = '0014_skills'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('''CREATE TABLE followups (
        id TEXT PRIMARY KEY,
        bot_id TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
        source_run_id TEXT,
        summary TEXT NOT NULL,
        due_at REAL NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('open','done')),
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL
    )''')
    op.execute('CREATE INDEX followups_due ON followups(status,due_at,id)')


def downgrade():
    raise RuntimeError('Funk Bot migrations are forward-only; restore a backup to downgrade.')
