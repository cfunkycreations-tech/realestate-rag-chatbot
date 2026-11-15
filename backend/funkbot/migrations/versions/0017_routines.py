"""Persist scheduled mission definitions and unique execution slots."""
from alembic import op
revision='0017_routines'
down_revision='0016_handoffs'
branch_labels=None
depends_on=None

def upgrade():
    op.execute('''CREATE TABLE routines (
        id TEXT PRIMARY KEY, title TEXT NOT NULL, instructions TEXT NOT NULL,
        bot_id TEXT REFERENCES bots(id) ON DELETE SET NULL, cron TEXT NOT NULL,
        timezone TEXT NOT NULL, paused INTEGER NOT NULL CHECK(paused IN (0,1)),
        next_at REAL NOT NULL, created_at REAL NOT NULL, updated_at REAL NOT NULL
    )''')
    op.execute('''CREATE TABLE routine_runs (
        id TEXT PRIMARY KEY, routine_id TEXT NOT NULL REFERENCES routines(id) ON DELETE CASCADE,
        mission_id TEXT NOT NULL UNIQUE REFERENCES missions(id) ON DELETE CASCADE,
        scheduled_at REAL, created_at REAL NOT NULL, approval TEXT NOT NULL CHECK(approval IN ('pending','approved','denied')), UNIQUE(routine_id,scheduled_at)
    )''')
    op.execute('CREATE INDEX routine_due ON routines(paused,next_at)')
    op.execute('CREATE INDEX routine_history ON routine_runs(routine_id,created_at DESC)')

def downgrade():
    raise RuntimeError('Funk Bot migrations are forward-only; restore a backup to downgrade.')
