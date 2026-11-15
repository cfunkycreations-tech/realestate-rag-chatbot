"""Persist tool proposals, decisions and execution audit entries."""
from alembic import op

revision = '0007_tool_audit'
down_revision = '0006_budget_reconciliation'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('''CREATE TABLE tool_calls (
        id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        bot_id TEXT NOT NULL,
        tool_name TEXT NOT NULL,
        risk TEXT NOT NULL CHECK(risk IN ('read','write')),
        arguments TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('pending','approved','denied','running','completed','failed')),
        result TEXT,
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL
    )''')
    op.execute('CREATE INDEX tool_calls_run_order ON tool_calls(run_id,created_at,id)')
    op.execute('''CREATE TABLE tool_audit (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        call_id TEXT NOT NULL,
        action TEXT NOT NULL,
        created_at REAL NOT NULL
    )''')
    op.execute('CREATE INDEX tool_audit_call_order ON tool_audit(call_id,id)')


def downgrade():
    raise RuntimeError('Funk Bot migrations are forward-only; restore a backup to downgrade.')
