"""Token wallets and Economy Mode: attribution, model flags and budget alerts.

New tables only; usage, budget_* and bots are untouched.
"""
from alembic import op

revision = '0032_economy'
down_revision = '0031_employee_dna'
branch_labels = None
depends_on = None


def upgrade():
    # One row per run, written in the same transaction as its reservation.
    # Rounds join through budget_reservations.parent_run_id.
    op.execute('''CREATE TABLE run_attribution (
        run_id TEXT PRIMARY KEY,
        bot_id TEXT NOT NULL,
        mission_id TEXT,
        project_id TEXT,
        delegated INTEGER NOT NULL DEFAULT 0,
        origin_bot_id TEXT,
        tier TEXT,
        requested_profile TEXT NOT NULL,
        effective_profile TEXT NOT NULL,
        adjustment TEXT,
        created_at REAL NOT NULL
    )''')
    op.execute('CREATE INDEX run_attribution_origin ON run_attribution(origin_bot_id, delegated)')
    op.execute('CREATE INDEX run_attribution_mission ON run_attribution(mission_id)')
    op.execute('CREATE INDEX run_attribution_project ON run_attribution(project_id)')
    # Which handoff mission came from which run, so delegated spend can be
    # followed to the Bot that originated it, at any depth.
    op.execute('''CREATE TABLE delegation_origins (
        mission_id TEXT PRIMARY KEY,
        origin_run_id TEXT NOT NULL,
        origin_bot_id TEXT NOT NULL,
        origin_profile TEXT NOT NULL,
        created_at REAL NOT NULL
    )''')
    # Owner attestations that one exact gateway+model is free or local.
    # Absent rows mean "billed at the profile price"; nothing is assumed free.
    op.execute('''CREATE TABLE model_flags (
        gateway TEXT NOT NULL,
        model TEXT NOT NULL,
        kind TEXT NOT NULL CHECK(kind IN ('free','local')),
        note TEXT NOT NULL DEFAULT '',
        verified_at REAL NOT NULL,
        PRIMARY KEY (gateway, model)
    )''')
    # Marks a settled round whose cost came from an owner attestation.
    op.execute('''CREATE TABLE usage_flags (
        usage_id INTEGER PRIMARY KEY REFERENCES usage(id) ON DELETE CASCADE,
        basis TEXT NOT NULL
    )''')
    op.execute('''CREATE TABLE budget_alerts (
        scope TEXT NOT NULL,
        period TEXT NOT NULL,
        period_start REAL NOT NULL,
        threshold INTEGER NOT NULL,
        fired_at REAL NOT NULL,
        PRIMARY KEY (scope, period, period_start, threshold)
    )''')


def downgrade():
    raise RuntimeError('Funk Bot migrations are forward-only; restore a backup to downgrade.')
