"""Persistent group chat transcripts and bounded sequential turns."""
from alembic import op
revision='0020_group_chats'
down_revision='0019_attachments'
branch_labels=None
depends_on=None


def upgrade():
    op.execute('''CREATE TABLE group_chats (
        id TEXT PRIMARY KEY, group_id TEXT NOT NULL REFERENCES bot_groups(id) ON DELETE CASCADE,
        name TEXT NOT NULL, created_at REAL NOT NULL, updated_at REAL NOT NULL
    )''')
    op.execute('''CREATE TABLE group_chat_turns (
        id TEXT PRIMARY KEY, chat_id TEXT NOT NULL REFERENCES group_chats(id) ON DELETE CASCADE,
        status TEXT NOT NULL CHECK(status IN ('queued','running','done','failed','cancelled')),
        error TEXT, active_run_id TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL
    )''')
    op.execute('''CREATE TABLE group_chat_messages (
        id TEXT PRIMARY KEY, chat_id TEXT NOT NULL REFERENCES group_chats(id) ON DELETE CASCADE,
        turn_id TEXT REFERENCES group_chat_turns(id) ON DELETE SET NULL,
        bot_id TEXT REFERENCES bots(id) ON DELETE SET NULL,
        role TEXT NOT NULL CHECK(role IN ('user','chief','member','summary')),
        content TEXT NOT NULL, run_id TEXT, created_at REAL NOT NULL
    )''')
    op.execute("CREATE UNIQUE INDEX one_live_group_turn ON group_chat_turns(chat_id) WHERE status IN ('queued','running')")
    op.execute('CREATE INDEX group_chat_order ON group_chat_messages(chat_id,created_at,id)')
    op.execute('CREATE INDEX group_chats_by_group ON group_chats(group_id,updated_at DESC,id)')


def downgrade():
    raise RuntimeError('Funk Bot migrations are forward-only; restore a backup to downgrade.')
