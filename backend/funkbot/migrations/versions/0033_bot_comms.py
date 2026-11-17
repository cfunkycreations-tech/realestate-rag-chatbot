"""Bot-initiated messaging: owner-approved communication links, thread metadata, audit log.

New tables only. bot_dms / bot_dm_turns / bot_dm_messages are untouched (their INSERTs are positional).
"""
from alembic import op

revision='0033_bot_comms'
down_revision='0032_economy'
branch_labels=None
depends_on=None


def upgrade():
    op.execute('''CREATE TABLE comm_links (
        from_bot_id TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
        to_bot_id TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
        created_at REAL NOT NULL, PRIMARY KEY(from_bot_id,to_bot_id),
        CHECK(from_bot_id<>to_bot_id)
    )''')
    op.execute('''CREATE TABLE bot_message_threads (
        dm_id TEXT PRIMARY KEY REFERENCES bot_dms(id) ON DELETE CASCADE,
        initiator_id TEXT, receiver_id TEXT, kind TEXT NOT NULL,
        origin_bot_id TEXT, origin_profile TEXT, origin_run_id TEXT, origin_mission_id TEXT,
        chain TEXT NOT NULL, created_at REAL NOT NULL
    )''')
    op.execute('''CREATE TABLE bot_message_log (
        id TEXT PRIMARY KEY, dm_id TEXT, sender_id TEXT, receiver_id TEXT, kind TEXT NOT NULL,
        body_hash TEXT NOT NULL, run_id TEXT, mission_id TEXT,
        status TEXT NOT NULL CHECK(status IN ('sent','replied','failed','expired','refused')),
        detail TEXT, created_at REAL NOT NULL
    )''')
    op.execute('CREATE INDEX bot_message_log_sender ON bot_message_log(sender_id,created_at)')
    op.execute('CREATE INDEX bot_message_log_pair ON bot_message_log(sender_id,receiver_id,created_at)')
    op.execute('CREATE INDEX bot_message_log_dm ON bot_message_log(dm_id)')


def downgrade():
    raise RuntimeError('Funk Bot migrations are forward-only; restore a backup to downgrade.')
