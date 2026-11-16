"""Default-deny, revisioned computer access per Bot."""
from alembic import op
revision='0025_computer_permissions'
down_revision='0024_computer_workspaces'
branch_labels=None
depends_on=None


def upgrade():
    op.execute('''CREATE TABLE computer_permissions (
        bot_id TEXT PRIMARY KEY REFERENCES bots(id) ON DELETE CASCADE,
        allowed INTEGER NOT NULL CHECK(allowed IN (0,1)),
        revision INTEGER NOT NULL CHECK(revision>0),
        updated_at REAL NOT NULL
    )''')


def downgrade():
    raise RuntimeError('Funk Bot migrations are forward-only; restore a backup to downgrade.')
