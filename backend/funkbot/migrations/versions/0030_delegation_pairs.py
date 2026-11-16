"""Owner pre-approved directional delegation pairs."""
from alembic import op
revision='0030_delegation_pairs'
down_revision='0029_learned_routine_drafts'
branch_labels=None
depends_on=None

def upgrade():
    op.execute('''CREATE TABLE delegation_pairs (
        from_bot_id TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
        to_bot_id TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
        created_at REAL NOT NULL, PRIMARY KEY(from_bot_id,to_bot_id),
        CHECK(from_bot_id<>to_bot_id)
    )''')

def downgrade(): raise RuntimeError('Funk Bot migrations are forward-only; restore a backup to downgrade.')
