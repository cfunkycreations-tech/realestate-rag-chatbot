"""Add owner-authored account skills without modifying existing records."""
from alembic import op

revision = '0014_skills'
down_revision = '0013_memory_layers'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('''CREATE TABLE skills (
        id TEXT PRIMARY KEY,
        slug TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        when_to_use TEXT NOT NULL,
        inputs TEXT NOT NULL,
        steps TEXT NOT NULL,
        checks TEXT NOT NULL,
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL
    )''')
    op.execute('CREATE INDEX skills_order ON skills(name,id)')


def downgrade():
    raise RuntimeError('Funk Bot migrations are forward-only; restore a backup to downgrade.')
