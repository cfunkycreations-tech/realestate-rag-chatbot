"""Add a cursor-ordered account event feed without changing old run events."""
from alembic import op

revision = '0002_event_log'
down_revision = '0001_adopt_slice2'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('''CREATE TABLE events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        bot_id TEXT REFERENCES bots(id) ON DELETE CASCADE,
        run_id TEXT REFERENCES runs(id) ON DELETE SET NULL,
        event_type TEXT NOT NULL,
        payload TEXT NOT NULL,
        created_at REAL NOT NULL
    )''')
    op.execute('CREATE INDEX events_bot_cursor ON events(bot_id, id)')


def downgrade():
    raise RuntimeError('Funk Bot migrations are forward-only; restore a backup to downgrade.')
