"""Relate future model-request reservations to their originating run."""
from alembic import op

revision = '0008_budget_rounds'
down_revision = '0007_tool_audit'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('ALTER TABLE budget_reservations ADD COLUMN parent_run_id TEXT')
    op.execute('UPDATE budget_reservations SET parent_run_id=run_id')
    op.execute('CREATE INDEX budget_reservations_parent ON budget_reservations(parent_run_id,status)')


def downgrade():
    raise RuntimeError('Funk Bot migrations are forward-only; restore a backup to downgrade.')
