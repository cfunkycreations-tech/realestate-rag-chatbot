"""Track which uploaded ZIP (pack) each Vault character came from."""
from alembic import op

revision = '0013_character_packs'
down_revision = '0012_lab_memory'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('''CREATE TABLE IF NOT EXISTS character_packs (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        normalized_name TEXT NOT NULL UNIQUE,
        file_name TEXT NOT NULL,
        file_hash TEXT NOT NULL UNIQUE,
        added INTEGER NOT NULL,
        duplicates INTEGER NOT NULL,
        invalid INTEGER NOT NULL,
        created_at REAL NOT NULL
    )''')
    # A link table keeps the original 10-column characters table untouched.
    op.execute('''CREATE TABLE IF NOT EXISTS pack_characters (
        character_id TEXT PRIMARY KEY REFERENCES characters(id) ON DELETE CASCADE,
        pack_id TEXT NOT NULL REFERENCES character_packs(id) ON DELETE CASCADE
    )''')
    op.execute('CREATE INDEX IF NOT EXISTS pack_characters_pack ON pack_characters(pack_id)')


def downgrade():
    raise RuntimeError('Funk Bot migrations are forward-only; restore a backup to downgrade.')
