"""Owner-corrected, versioned workflow templates and immutable replay snapshots."""
from alembic import op
revision='0022_workflows'
down_revision='0021_work_artifacts'
branch_labels=None
depends_on=None


def upgrade():
    op.execute('''CREATE TABLE workflows (
        id TEXT PRIMARY KEY, source_mission_id TEXT REFERENCES missions(id) ON DELETE SET NULL,
        current_version INTEGER NOT NULL CHECK(current_version>0), created_at REAL NOT NULL, updated_at REAL NOT NULL
    )''')
    op.execute('''CREATE TABLE workflow_versions (
        workflow_id TEXT NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
        version INTEGER NOT NULL CHECK(version>0), name TEXT NOT NULL,
        bot_id TEXT REFERENCES bots(id) ON DELETE SET NULL,
        steps TEXT NOT NULL, change_note TEXT NOT NULL, created_at REAL NOT NULL,
        PRIMARY KEY(workflow_id,version)
    )''')
    op.execute('''CREATE TABLE workflow_replays (
        mission_id TEXT PRIMARY KEY REFERENCES missions(id) ON DELETE CASCADE,
        workflow_id TEXT REFERENCES workflows(id) ON DELETE SET NULL,
        version INTEGER NOT NULL, steps TEXT NOT NULL, created_at REAL NOT NULL
    )''')
    op.execute('CREATE INDEX workflows_recent ON workflows(updated_at DESC,id)')
    op.execute('CREATE INDEX workflow_replays_history ON workflow_replays(workflow_id,created_at DESC)')


def downgrade():
    raise RuntimeError('Funk Bot migrations are forward-only; restore a backup to downgrade.')
