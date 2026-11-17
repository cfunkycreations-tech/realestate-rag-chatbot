"""Phase 5b: owner-approval queue for Bot-originated mentorship and training requests.

New table only; nothing here is read by tool policies, budgets, model tiers or the Vault.
A request changes nothing until the owner approves it.
"""
from alembic import op

revision='0035_family_automation'
down_revision='0034_family_council'
branch_labels=None
depends_on=None


def upgrade():
    op.execute("""CREATE TABLE family_requests (
        id TEXT PRIMARY KEY,
        kind TEXT NOT NULL CHECK(kind IN ('mentorship','training_mission')),
        bot_id TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
        other_bot_id TEXT REFERENCES bots(id) ON DELETE CASCADE,
        payload_json TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('pending','approved','rejected','withdrawn')),
        decision_note TEXT NOT NULL DEFAULT '',
        created_at REAL NOT NULL, decided_at REAL)""")
    op.execute("CREATE UNIQUE INDEX family_requests_one_pending ON family_requests(kind,bot_id,COALESCE(other_bot_id,'')) WHERE status='pending'")
    op.execute('CREATE INDEX family_requests_status ON family_requests(status,created_at)')
