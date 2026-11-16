"""Employee DNA: versioned role presets, per-bot Career DNA snapshot and career history."""
from alembic import op
revision='0031_employee_dna'
down_revision='0030_delegation_pairs'
branch_labels=None
depends_on=None

def upgrade():
    op.execute('''CREATE TABLE IF NOT EXISTS role_presets (
        id TEXT PRIMARY KEY, department TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'active',
        current_version INTEGER NOT NULL, customized INTEGER NOT NULL DEFAULT 0,
        created_at REAL NOT NULL, updated_at REAL NOT NULL,
        CHECK(status IN ('active','retired'))
    )''')
    op.execute('''CREATE TABLE IF NOT EXISTS role_preset_versions (
        preset_id TEXT NOT NULL REFERENCES role_presets(id) ON DELETE CASCADE,
        version INTEGER NOT NULL, data TEXT NOT NULL, content_hash TEXT NOT NULL,
        source TEXT NOT NULL, created_at REAL NOT NULL, PRIMARY KEY(preset_id,version)
    )''')
    op.execute('CREATE INDEX IF NOT EXISTS idx_role_preset_hash ON role_preset_versions(content_hash)')
    op.execute('''CREATE TABLE IF NOT EXISTS bot_careers (
        bot_id TEXT PRIMARY KEY REFERENCES bots(id) ON DELETE CASCADE,
        preset_id TEXT NOT NULL, preset_version INTEGER NOT NULL, career_json TEXT NOT NULL,
        level TEXT NOT NULL, department TEXT NOT NULL, model_tier TEXT NOT NULL,
        mentor_bot_id TEXT REFERENCES bots(id) ON DELETE SET NULL, installed_at REAL NOT NULL
    )''')
    op.execute('''CREATE TABLE IF NOT EXISTS career_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        bot_id TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
        event TEXT NOT NULL, detail TEXT NOT NULL, created_at REAL NOT NULL
    )''')
    op.execute('CREATE INDEX IF NOT EXISTS idx_career_history_bot ON career_history(bot_id,id)')

def downgrade(): raise RuntimeError('Funk Bot migrations are forward-only; restore a backup to downgrade.')
