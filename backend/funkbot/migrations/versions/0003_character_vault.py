"""Private character catalog and Bot assignments."""
from alembic import op

revision = '0003_character_vault'
down_revision = '0002_event_log'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('''CREATE TABLE characters (
        id TEXT PRIMARY KEY,
        content_hash TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        normalized_name TEXT NOT NULL UNIQUE,
        role TEXT NOT NULL,
        tags TEXT NOT NULL,
        notes TEXT NOT NULL,
        rarity TEXT NOT NULL,
        drawn INTEGER NOT NULL DEFAULT 0,
        created_at REAL NOT NULL
    )''')
    op.execute('CREATE INDEX character_draw_bucket ON characters(drawn,rarity)')
    op.execute('''CREATE TABLE bot_characters (
        bot_id TEXT PRIMARY KEY REFERENCES bots(id) ON DELETE CASCADE,
        character_id TEXT NOT NULL REFERENCES characters(id),
        assigned_at REAL NOT NULL
    )''')
    op.execute('CREATE INDEX character_assigned ON bot_characters(character_id)')


def downgrade():
    raise RuntimeError('Funk Bot migrations are forward-only; restore a backup to downgrade.')
