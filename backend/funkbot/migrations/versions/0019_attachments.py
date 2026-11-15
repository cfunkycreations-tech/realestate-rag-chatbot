"""Store owner-uploaded chat attachments inside the workspace database."""
from alembic import op
revision='0019_attachments'
down_revision='0018_chats'
branch_labels=None
depends_on=None

def upgrade():
    op.execute('''CREATE TABLE chat_attachments (
        id TEXT PRIMARY KEY, chat_id TEXT NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
        message_id TEXT REFERENCES messages(id) ON DELETE CASCADE,
        name TEXT NOT NULL, media_type TEXT NOT NULL, data BLOB NOT NULL,
        extracted TEXT, created_at REAL NOT NULL
    )''')
    op.execute('CREATE INDEX attachments_chat ON chat_attachments(chat_id,created_at,id)')
    op.execute('CREATE INDEX attachments_message ON chat_attachments(message_id,id)')

def downgrade():
    raise RuntimeError('Funk Bot migrations are forward-only; restore a backup to downgrade.')
