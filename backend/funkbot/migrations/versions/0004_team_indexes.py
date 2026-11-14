"""Add lookup indexes for larger Bot rosters and event-driven team statistics."""
from alembic import op

revision = '0004_team_indexes'
down_revision = '0003_character_vault'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('CREATE INDEX IF NOT EXISTS messages_bot_time ON messages(bot_id, created_at DESC)')
    op.execute('CREATE INDEX IF NOT EXISTS events_type_time ON events(event_type, created_at)')
    op.execute('CREATE INDEX IF NOT EXISTS events_type_bot_cursor ON events(event_type, bot_id, id DESC)')


def downgrade():
    raise RuntimeError('Funk Bot migrations are forward-only; restore a backup to downgrade.')
