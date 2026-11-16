"""Remember automatic routine retry attempts across restarts."""
from alembic import op
revision='0028_routine_retries'
down_revision='0027_inbox_notices'
branch_labels=None
depends_on=None

def upgrade():
    op.execute('ALTER TABLE routine_runs ADD COLUMN retry_count INTEGER NOT NULL DEFAULT 0')
    op.execute('ALTER TABLE routine_runs ADD COLUMN failure_notified INTEGER NOT NULL DEFAULT 0')

def downgrade(): raise RuntimeError('Funk Bot migrations are forward-only; restore a backup to downgrade.')
