"""Phase 5: career levels, reviews, promotion recommendations, mentorship, Family Council.

New tables only. Career *levels* here are descriptive labels: nothing in this schema is
read by tool policies, budgets, model tiers or the Vault, so changing a level cannot
change authority. History reuses career_history (0031); no parallel history table.
"""
from alembic import op

revision='0034_family_council'
down_revision='0033_bot_comms'
branch_labels=None
depends_on=None

LEVELS="'trainee','junior','specialist','senior','lead','principal'"


def upgrade():
    op.execute(f'''CREATE TABLE career_levels (
        bot_id TEXT PRIMARY KEY REFERENCES bots(id) ON DELETE CASCADE,
        level TEXT NOT NULL CHECK(level IN ({LEVELS})), since REAL NOT NULL
    )''')
    # Only the owner sets this. A mission with status done is the Bot's own report, not verified quality.
    op.execute('''CREATE TABLE mission_verifications (
        mission_id TEXT PRIMARY KEY REFERENCES missions(id) ON DELETE CASCADE,
        verdict TEXT NOT NULL CHECK(verdict IN ('verified','rejected')),
        note TEXT NOT NULL DEFAULT '', created_at REAL NOT NULL
    )''')
    op.execute('''CREATE TABLE reviews (
        id TEXT PRIMARY KEY,
        bot_id TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
        kind TEXT NOT NULL CHECK(kind IN ('periodic','mission')),
        period_key TEXT NOT NULL, level TEXT NOT NULL,
        metrics_json TEXT NOT NULL, evidence_json TEXT NOT NULL,
        strengths_json TEXT NOT NULL, development_json TEXT NOT NULL, eligibility_json TEXT NOT NULL,
        created_at REAL NOT NULL, UNIQUE(bot_id,kind,period_key)
    )''')
    op.execute('CREATE INDEX reviews_bot ON reviews(bot_id,created_at DESC)')
    # Feedback is shown beside a review but is never part of the eligibility arithmetic.
    op.execute('''CREATE TABLE review_feedback (
        id TEXT PRIMARY KEY,
        review_id TEXT NOT NULL REFERENCES reviews(id) ON DELETE CASCADE,
        from_bot_id TEXT REFERENCES bots(id) ON DELETE SET NULL, from_name TEXT NOT NULL,
        role TEXT NOT NULL CHECK(role IN ('mentor','peer','owner')),
        rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
        comment TEXT NOT NULL, created_at REAL NOT NULL
    )''')
    op.execute("CREATE UNIQUE INDEX review_feedback_once ON review_feedback(review_id,from_bot_id) WHERE from_bot_id IS NOT NULL")
    op.execute(f'''CREATE TABLE promotion_recommendations (
        id TEXT PRIMARY KEY,
        bot_id TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
        from_level TEXT NOT NULL CHECK(from_level IN ({LEVELS})),
        to_level TEXT NOT NULL CHECK(to_level IN ({LEVELS})),
        source TEXT NOT NULL CHECK(source IN ('system','bot','owner')),
        proposer_bot_id TEXT REFERENCES bots(id) ON DELETE SET NULL,
        review_id TEXT REFERENCES reviews(id) ON DELETE SET NULL,
        rationale TEXT NOT NULL, evidence_json TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('pending','approved','rejected','withdrawn')),
        decision_note TEXT NOT NULL DEFAULT '', created_at REAL NOT NULL, decided_at REAL
    )''')
    op.execute("CREATE UNIQUE INDEX promotion_one_pending ON promotion_recommendations(bot_id) WHERE status='pending'")
    op.execute('''CREATE TABLE mentorships (
        id TEXT PRIMARY KEY,
        mentor_id TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
        trainee_id TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
        status TEXT NOT NULL CHECK(status IN ('active','graduated','ended')),
        objectives_json TEXT NOT NULL, criteria_json TEXT NOT NULL,
        note TEXT NOT NULL DEFAULT '', created_at REAL NOT NULL, ended_at REAL,
        CHECK(mentor_id<>trainee_id)
    )''')
    op.execute("CREATE UNIQUE INDEX mentorship_one_active ON mentorships(trainee_id) WHERE status='active'")
    op.execute('''CREATE TABLE training_missions (
        mission_id TEXT PRIMARY KEY REFERENCES missions(id) ON DELETE CASCADE,
        mentorship_id TEXT NOT NULL REFERENCES mentorships(id) ON DELETE CASCADE,
        objective_idx INTEGER NOT NULL CHECK(objective_idx>=0), cap_usd TEXT NOT NULL, created_at REAL NOT NULL
    )''')
    op.execute('''CREATE TABLE council_members (
        bot_id TEXT PRIMARY KEY REFERENCES bots(id) ON DELETE CASCADE, added_at REAL NOT NULL
    )''')
    op.execute('''CREATE TABLE council_meetings (
        id TEXT PRIMARY KEY,
        trigger TEXT NOT NULL CHECK(trigger IN ('manual','scheduled')),
        status TEXT NOT NULL CHECK(status IN ('planned','running','done','failed','cancelled')),
        proposal_ids_json TEXT NOT NULL, member_ids_json TEXT NOT NULL,
        cap_nanos INTEGER NOT NULL, estimate_nanos INTEGER NOT NULL,
        created_at REAL NOT NULL, started_at REAL, finished_at REAL, error TEXT
    )''')
    op.execute('''CREATE TABLE council_proposals (
        id TEXT PRIMARY KEY, title TEXT NOT NULL, body TEXT NOT NULL,
        kind TEXT NOT NULL CHECK(kind IN ('workflow','training','mentorship','promotion','budget','permission','publication','destructive','security','organization','other')),
        proposer TEXT NOT NULL, proposer_bot_id TEXT REFERENCES bots(id) ON DELETE SET NULL,
        status TEXT NOT NULL CHECK(status IN ('open','passed','rejected','escalated','withdrawn','owner_approved','owner_rejected')),
        requires_owner INTEGER NOT NULL CHECK(requires_owner IN (0,1)),
        tally_json TEXT, rationale TEXT NOT NULL DEFAULT '', meeting_id TEXT REFERENCES council_meetings(id) ON DELETE SET NULL,
        created_at REAL NOT NULL, decided_at REAL
    )''')
    op.execute('''CREATE TABLE council_votes (
        id TEXT PRIMARY KEY,
        proposal_id TEXT NOT NULL REFERENCES council_proposals(id) ON DELETE CASCADE,
        meeting_id TEXT REFERENCES council_meetings(id) ON DELETE SET NULL,
        voter_bot_id TEXT REFERENCES bots(id) ON DELETE SET NULL, voter_name TEXT NOT NULL,
        vote TEXT NOT NULL CHECK(vote IN ('approve','reject','abstain')),
        rationale TEXT NOT NULL, evidence_json TEXT NOT NULL, created_at REAL NOT NULL
    )''')
    op.execute("CREATE UNIQUE INDEX council_vote_once ON council_votes(proposal_id,voter_bot_id) WHERE voter_bot_id IS NOT NULL")
    # A vote, once cast, cannot be changed or re-pointed (history stays intact if a Bot is later deleted).
    op.execute('''CREATE TRIGGER council_votes_immutable BEFORE UPDATE OF proposal_id,vote,rationale,evidence_json,voter_name,created_at ON council_votes
        BEGIN SELECT RAISE(ABORT,'Votes cannot be changed.'); END''')


def downgrade(): raise RuntimeError('Funk Bot migrations are forward-only; restore a backup to downgrade.')
