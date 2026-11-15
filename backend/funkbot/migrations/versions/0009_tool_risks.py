"""Extend approval risk categories while retaining tool history and row order."""
from alembic import op

revision = '0009_tool_risks'
down_revision = '0008_budget_rounds'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('''CREATE TABLE tool_calls_new (
        id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        bot_id TEXT NOT NULL,
        tool_name TEXT NOT NULL,
        risk TEXT NOT NULL CHECK(risk IN ('read','write','send','spend')),
        arguments TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('pending','approved','denied','running','completed','failed')),
        result TEXT,
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL
    )''')
    # Preserve rowids: account audit pagination uses them as stable cursors.
    op.execute('''INSERT INTO tool_calls_new (rowid,id,run_id,bot_id,tool_name,risk,arguments,status,result,created_at,updated_at)
                  SELECT rowid,id,run_id,bot_id,tool_name,risk,arguments,status,result,created_at,updated_at FROM tool_calls''')
    op.execute('DROP TABLE tool_calls')
    op.execute('ALTER TABLE tool_calls_new RENAME TO tool_calls')
    op.execute('CREATE INDEX tool_calls_run_order ON tool_calls(run_id,created_at,id)')


def downgrade():
    raise RuntimeError('Funk Bot migrations are forward-only; restore a backup to downgrade.')
