"""Bounded per-Bot computer workspace snapshots."""
from alembic import op
revision='0024_computer_workspaces'
down_revision='0023_bot_dms'
branch_labels=None
depends_on=None


def upgrade():
    op.execute('''CREATE TABLE computer_workspaces (
        bot_id TEXT PRIMARY KEY REFERENCES bots(id) ON DELETE CASCADE,
        snapshot TEXT NOT NULL,
        updated_at REAL NOT NULL
    )''')


def downgrade():
    raise RuntimeError('Funk Bot migrations are forward-only; restore a backup to downgrade.')
