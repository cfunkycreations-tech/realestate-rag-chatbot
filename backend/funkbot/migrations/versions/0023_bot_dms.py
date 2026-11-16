"""Persistent owner-initiated Bot-to-Bot conversations."""
from alembic import op
revision='0023_bot_dms'
down_revision='0022_workflows'
branch_labels=None
depends_on=None


def upgrade():
    op.execute('''CREATE TABLE bot_dms (
        id TEXT PRIMARY KEY, name TEXT NOT NULL,
        sender_id TEXT REFERENCES bots(id) ON DELETE SET NULL,
        receiver_id TEXT REFERENCES bots(id) ON DELETE SET NULL,
        created_at REAL NOT NULL, updated_at REAL NOT NULL
    )''')
    op.execute('''CREATE TABLE bot_dm_turns (
        id TEXT PRIMARY KEY, dm_id TEXT NOT NULL REFERENCES bot_dms(id) ON DELETE CASCADE,
        status TEXT NOT NULL CHECK(status IN ('queued','running','done','failed','cancelled')),
        error TEXT, active_run_id TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL
    )''')
    op.execute('''CREATE TABLE bot_dm_messages (
        id TEXT PRIMARY KEY, dm_id TEXT NOT NULL REFERENCES bot_dms(id) ON DELETE CASCADE,
        turn_id TEXT REFERENCES bot_dm_turns(id) ON DELETE SET NULL,
        bot_id TEXT REFERENCES bots(id) ON DELETE SET NULL,
        role TEXT NOT NULL CHECK(role IN ('user','sender','receiver')),
        content TEXT NOT NULL, run_id TEXT, created_at REAL NOT NULL
    )''')
    op.execute("CREATE UNIQUE INDEX one_live_dm_turn ON bot_dm_turns(dm_id) WHERE status IN ('queued','running')")
    op.execute('CREATE INDEX bot_dm_messages_order ON bot_dm_messages(dm_id,created_at,id)')
    op.execute('CREATE INDEX bot_dm_recent ON bot_dms(updated_at DESC,id)')


def downgrade():
    raise RuntimeError('Funk Bot migrations are forward-only; restore a backup to downgrade.')
