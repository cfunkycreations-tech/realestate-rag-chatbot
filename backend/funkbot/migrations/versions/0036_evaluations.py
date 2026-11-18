"""Phase 6: recorded evaluation results, derived certification labels and instruction version history.

New tables only. Nothing here is read by tool policies, budgets, model tiers or the Vault:
a certification is a label and an instruction version is a saved copy of text the owner already controls.
"""
from alembic import op

revision = '0036_evaluations'
down_revision = '0035_family_automation'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('''CREATE TABLE evaluation_results (
        id TEXT PRIMARY KEY,
        bot_id TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
        suite TEXT NOT NULL, suite_version INTEGER NOT NULL,
        mode TEXT NOT NULL CHECK(mode IN ('live','simulated')),
        status TEXT NOT NULL CHECK(status IN ('passed','failed')),
        score INTEGER NOT NULL, pass_mark INTEGER NOT NULL,
        counts INTEGER NOT NULL CHECK(counts IN (0,1)),
        evidence_json TEXT NOT NULL, cause TEXT NOT NULL DEFAULT '',
        cost_nanos INTEGER NOT NULL DEFAULT 0, created_at REAL NOT NULL
    )''')
    op.execute('CREATE INDEX evaluation_results_bot ON evaluation_results(bot_id,suite,created_at DESC)')
    op.execute('''CREATE TABLE evaluation_certs (
        bot_id TEXT PRIMARY KEY REFERENCES bots(id) ON DELETE CASCADE,
        level TEXT NOT NULL CHECK(level IN ('not_evaluated','training','competent','advanced','expert')),
        updated_at REAL NOT NULL
    )''')
    op.execute('''CREATE TABLE bot_instruction_versions (
        id TEXT PRIMARY KEY,
        bot_id TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
        personality TEXT NOT NULL, source TEXT NOT NULL, reason TEXT NOT NULL DEFAULT '',
        scores_json TEXT NOT NULL DEFAULT '{}', created_at REAL NOT NULL
    )''')
    op.execute('CREATE INDEX instruction_versions_bot ON bot_instruction_versions(bot_id,created_at DESC)')


def downgrade():
    raise RuntimeError('Funk Bot migrations are forward-only; restore a backup to downgrade.')
