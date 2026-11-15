"""Store bounded mission and project file snapshots in the workspace database."""
from alembic import op
revision='0021_work_artifacts'
down_revision='0020_group_chats'
branch_labels=None
depends_on=None


def upgrade():
    op.execute('''CREATE TABLE work_artifacts (
        id TEXT PRIMARY KEY,
        mission_id TEXT REFERENCES missions(id) ON DELETE CASCADE,
        project_id TEXT REFERENCES projects(id) ON DELETE CASCADE,
        bot_id TEXT REFERENCES bots(id) ON DELETE SET NULL,
        run_id TEXT REFERENCES runs(id) ON DELETE SET NULL,
        name TEXT NOT NULL, data BLOB NOT NULL, created_at REAL NOT NULL,
        CHECK ((mission_id IS NOT NULL AND project_id IS NULL) OR (project_id IS NOT NULL AND mission_id IS NULL))
    )''')
    op.execute('CREATE INDEX work_artifacts_mission ON work_artifacts(mission_id,created_at,id)')
    op.execute('CREATE INDEX work_artifacts_project ON work_artifacts(project_id,created_at,id)')


def downgrade():
    raise RuntimeError('Funk Bot migrations are forward-only; restore a backup to downgrade.')
