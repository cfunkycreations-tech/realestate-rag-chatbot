"""Add provenance and isolated shared/project memory without modifying existing facts."""
from alembic import op

revision = '0013_memory_layers'
down_revision = '0013_character_packs'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE bot_memories ADD COLUMN source TEXT NOT NULL DEFAULT 'owner'")
    op.execute('ALTER TABLE bot_memories ADD COLUMN source_ref TEXT')
    op.execute('''CREATE TABLE shared_memories (
        id TEXT PRIMARY KEY,
        content TEXT NOT NULL,
        source TEXT NOT NULL,
        source_ref TEXT,
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL
    )''')
    op.execute('''CREATE TABLE project_memories (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        content TEXT NOT NULL,
        source TEXT NOT NULL,
        source_ref TEXT,
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL
    )''')
    op.execute('CREATE INDEX project_memories_order ON project_memories(project_id,updated_at DESC,id)')


def downgrade():
    raise RuntimeError('Funk Bot migrations are forward-only; restore a backup to downgrade.')
