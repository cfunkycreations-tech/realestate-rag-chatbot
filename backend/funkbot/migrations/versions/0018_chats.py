"""Introduce per-Bot chat threads while retaining all existing history."""
from alembic import op
revision='0018_chats'
down_revision='0017_routines'
branch_labels=None
depends_on=None

def upgrade():
    op.execute('''CREATE TABLE chats (
        id TEXT PRIMARY KEY, bot_id TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
        name TEXT NOT NULL, created_at REAL NOT NULL, updated_at REAL NOT NULL
    )''')
    op.execute('''CREATE TABLE chat_messages (
        chat_id TEXT NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
        message_id TEXT NOT NULL UNIQUE REFERENCES messages(id) ON DELETE CASCADE,
        PRIMARY KEY(chat_id,message_id)
    )''')
    op.execute('''CREATE TABLE chat_runs (
        chat_id TEXT NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
        run_id TEXT NOT NULL UNIQUE REFERENCES runs(id) ON DELETE CASCADE,
        PRIMARY KEY(chat_id,run_id)
    )''')
    op.execute("INSERT INTO chats SELECT 'legacy-'||id,id,'Conversation',created_at,created_at FROM bots")
    op.execute("INSERT INTO chat_messages SELECT 'legacy-'||bot_id,id FROM messages")
    op.execute("INSERT INTO chat_runs SELECT 'legacy-'||bot_id,id FROM runs")
    op.execute('CREATE INDEX chats_by_bot ON chats(bot_id,updated_at DESC,id)')

def downgrade():
    raise RuntimeError('Funk Bot migrations are forward-only; restore a backup to downgrade.')
