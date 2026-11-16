"""Queue budgeted model drafting from repeated mission transcripts."""
from alembic import op
revision='0029_learned_routine_drafts'
down_revision='0028_routine_retries'
branch_labels=None
depends_on=None

def upgrade():
    op.execute('''CREATE TABLE routine_learning (
        id TEXT PRIMARY KEY, bot_id TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
        fingerprint TEXT NOT NULL, transcripts TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('queued','running','done','failed')),
        created_at REAL NOT NULL, UNIQUE(bot_id,fingerprint)
    )''')
    op.execute('''CREATE TABLE routine_learning_examples (
        mission_id TEXT PRIMARY KEY REFERENCES missions(id) ON DELETE CASCADE,
        learning_id TEXT NOT NULL REFERENCES routine_learning(id) ON DELETE CASCADE
    )''')

def downgrade(): raise RuntimeError('Funk Bot migrations are forward-only; restore a backup to downgrade.')
