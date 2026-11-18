"""Per-Bot model pin: the owner picks one exact model for a Bot. New table only; no limit, price or permission lives here."""
from alembic import op

revision = '0037_model_pin'
down_revision = '0036_evaluations'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('''CREATE TABLE bot_model_pins (
        bot_id TEXT PRIMARY KEY REFERENCES bots(id) ON DELETE CASCADE,
        gateway TEXT NOT NULL CHECK(gateway IN ('omniroute','openrouter','custom')),
        model TEXT NOT NULL, updated_at REAL NOT NULL
    )''')
