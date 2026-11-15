"""Add projects without modifying existing mission or Bot records."""
from alembic import op

revision = '0011_projects'
down_revision = '0010_missions'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('''CREATE TABLE projects (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        description TEXT NOT NULL,
        owner_bot_id TEXT REFERENCES bots(id) ON DELETE SET NULL,
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL
    )''')
    op.execute('''CREATE TABLE project_missions (
        project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        mission_id TEXT NOT NULL REFERENCES missions(id) ON DELETE CASCADE,
        added_at REAL NOT NULL,
        PRIMARY KEY(project_id,mission_id),
        UNIQUE(mission_id)
    )''')
    op.execute('''CREATE TABLE project_notes (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        content TEXT NOT NULL,
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL
    )''')
    op.execute('CREATE INDEX projects_recent ON projects(updated_at DESC,id)')
    op.execute('CREATE INDEX project_notes_order ON project_notes(project_id,created_at,id)')


def downgrade():
    raise RuntimeError('Funk Bot migrations are forward-only; restore a backup to downgrade.')
