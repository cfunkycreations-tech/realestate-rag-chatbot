"""Audit owner-supplied corrections for otherwise unknown gateway charges."""
from alembic import op

revision = '0006_budget_reconciliation'
down_revision = '0005_budget_foundation'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('''CREATE TABLE budget_reconciliations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id TEXT UNIQUE,
        usage_id INTEGER UNIQUE,
        cost_nanos INTEGER NOT NULL CHECK(cost_nanos >= 0),
        note TEXT NOT NULL,
        created_at REAL NOT NULL,
        CHECK(run_id IS NOT NULL OR usage_id IS NOT NULL)
    )''')


def downgrade():
    raise RuntimeError('Funk Bot migrations are forward-only; restore a backup to downgrade.')
