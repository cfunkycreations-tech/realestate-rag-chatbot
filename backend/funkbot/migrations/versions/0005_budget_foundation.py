"""Add budget configuration and reservation records without changing existing data."""
from alembic import op

revision = '0005_budget_foundation'
down_revision = '0004_team_indexes'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('''CREATE TABLE budget_limits (
        scope TEXT PRIMARY KEY,
        daily_nanos INTEGER NOT NULL CHECK(daily_nanos >= 0),
        monthly_nanos INTEGER CHECK(monthly_nanos IS NULL OR monthly_nanos >= 0)
    )''')
    op.execute('''CREATE TABLE budget_prices (
        profile TEXT PRIMARY KEY,
        prompt_usd_per_million TEXT NOT NULL,
        completion_usd_per_million TEXT NOT NULL,
        max_prompt_tokens INTEGER NOT NULL CHECK(max_prompt_tokens > 0),
        max_completion_tokens INTEGER NOT NULL CHECK(max_completion_tokens > 0)
    )''')
    op.execute('''CREATE TABLE budget_reservations (
        run_id TEXT PRIMARY KEY,
        bot_id TEXT NOT NULL,
        profile TEXT NOT NULL,
        created_at REAL NOT NULL,
        reserved_nanos INTEGER NOT NULL CHECK(reserved_nanos >= 0),
        actual_nanos INTEGER CHECK(actual_nanos IS NULL OR actual_nanos >= 0),
        settled_at REAL,
        prompt_usd_per_million TEXT NOT NULL,
        completion_usd_per_million TEXT NOT NULL,
        max_prompt_tokens INTEGER NOT NULL,
        max_completion_tokens INTEGER NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('reserved','settled','uncertain','released')),
        usage_id INTEGER UNIQUE REFERENCES usage(id) ON DELETE SET NULL
    )''')
    op.execute('CREATE INDEX budget_reservations_period ON budget_reservations(created_at, bot_id, status)')


def downgrade():
    raise RuntimeError('Funk Bot migrations are forward-only; restore a backup to downgrade.')
