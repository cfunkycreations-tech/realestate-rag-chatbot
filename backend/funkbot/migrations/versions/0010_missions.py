"""Add durable mission and group records without changing existing runs."""
from alembic import op

revision = '0010_missions'
down_revision = '0009_tool_risks'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('''CREATE TABLE bot_groups (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        chief_bot_id TEXT REFERENCES bots(id) ON DELETE SET NULL,
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL
    )''')
    op.execute('''CREATE TABLE bot_group_members (
        group_id TEXT NOT NULL REFERENCES bot_groups(id) ON DELETE CASCADE,
        bot_id TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
        position INTEGER NOT NULL CHECK(position >= 0 AND position < 6),
        PRIMARY KEY(group_id,bot_id),
        UNIQUE(group_id,position)
    )''')
    op.execute('''CREATE TABLE missions (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        instructions TEXT NOT NULL,
        group_id TEXT REFERENCES bot_groups(id) ON DELETE SET NULL,
        status TEXT NOT NULL CHECK(status IN ('queued','running','waiting_approval','done','failed','cancelled')),
        result TEXT,
        error TEXT,
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL
    )''')
    op.execute('''CREATE TABLE mission_assignees (
        mission_id TEXT NOT NULL REFERENCES missions(id) ON DELETE CASCADE,
        position INTEGER NOT NULL CHECK(position >= 0 AND position < 6),
        bot_id TEXT REFERENCES bots(id) ON DELETE SET NULL,
        PRIMARY KEY(mission_id,position),
        UNIQUE(mission_id,bot_id)
    )''')
    # run_id is intentionally retained when a Bot is deleted (runs cascade),
    # so the immutable budget ledger can still be attributed to the mission.
    op.execute('''CREATE TABLE mission_runs (
        id TEXT PRIMARY KEY,
        mission_id TEXT NOT NULL REFERENCES missions(id) ON DELETE CASCADE,
        bot_id TEXT REFERENCES bots(id) ON DELETE SET NULL,
        run_id TEXT UNIQUE,
        role TEXT NOT NULL CHECK(role IN ('member','chief')),
        status TEXT NOT NULL CHECK(status IN ('queued','running','waiting_approval','done','failed','cancelled')),
        result TEXT,
        error TEXT,
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL
    )''')
    op.execute('CREATE INDEX missions_recent ON missions(created_at DESC,id)')
    op.execute('CREATE INDEX mission_runs_order ON mission_runs(mission_id,created_at,id)')
    op.execute('CREATE INDEX mission_runs_live ON mission_runs(run_id,status)')


def downgrade():
    raise RuntimeError('Funk Bot migrations are forward-only; restore a backup to downgrade.')
