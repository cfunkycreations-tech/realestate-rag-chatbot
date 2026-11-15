"""Add Bot memory and persistent, isolated Lab comparisons."""
from alembic import op

revision = '0012_lab_memory'
down_revision = '0011_projects'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('''CREATE TABLE bot_memories (
        id TEXT PRIMARY KEY,
        bot_id TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
        content TEXT NOT NULL,
        pinned INTEGER NOT NULL DEFAULT 0 CHECK(pinned IN (0,1)),
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL
    )''')
    op.execute('CREATE INDEX bot_memories_order ON bot_memories(bot_id,pinned DESC,updated_at DESC,id)')
    op.execute('''CREATE TABLE lab_experiments (
        id TEXT PRIMARY KEY,
        bot_id TEXT REFERENCES bots(id) ON DELETE SET NULL,
        prompt TEXT NOT NULL,
        system_prompt TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('queued','running','done','failed','cancelled')),
        error TEXT,
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL
    )''')
    op.execute('''CREATE TABLE lab_runs (
        id TEXT PRIMARY KEY,
        experiment_id TEXT NOT NULL REFERENCES lab_experiments(id) ON DELETE CASCADE,
        position INTEGER NOT NULL CHECK(position >= 0 AND position < 3),
        profile TEXT NOT NULL,
        run_id TEXT UNIQUE,
        status TEXT NOT NULL CHECK(status IN ('queued','running','done','failed','cancelled')),
        result TEXT,
        error TEXT,
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL,
        UNIQUE(experiment_id,position)
    )''')
    op.execute('CREATE INDEX lab_experiments_recent ON lab_experiments(created_at DESC,id)')


def downgrade():
    raise RuntimeError('Funk Bot migrations are forward-only; restore a backup to downgrade.')
