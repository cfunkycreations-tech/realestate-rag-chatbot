import pytest
from sqlalchemy.exc import IntegrityError
import app as service


def test_group_slots_are_unique_and_limited_to_six():
    with service.db() as db:
        db.execute("INSERT INTO bot_groups VALUES ('g','Group',NULL,1,1)")
        for i in range(7): db.execute('INSERT INTO bots VALUES (?,?,?,?,?,?,?,?)',(str(i),'Bot','Editor','','mint','round','smart',1))
        for i in range(6): db.execute('INSERT INTO bot_group_members VALUES (?,?,?)',('g',str(i),i))
        with pytest.raises(IntegrityError): db.execute("INSERT INTO bot_group_members VALUES ('g','6',6)")
        with pytest.raises(IntegrityError): db.execute("INSERT INTO bot_group_members VALUES ('g','6',0)")
        assert db.execute('SELECT COUNT(*) FROM bot_group_members').fetchone()[0]==6


def test_deleted_bot_keeps_mission_history_and_ledger_reference():
    with service.db() as db:
        db.execute("INSERT INTO bots VALUES ('b','Bot','Editor','','mint','round','smart',1)")
        db.execute("INSERT INTO runs VALUES ('run','b','done',1,2)")
        db.execute("INSERT INTO bot_groups VALUES ('g','Group','b',1,1)")
        db.execute("INSERT INTO bot_group_members VALUES ('g','b',0)")
        db.execute("INSERT INTO missions VALUES ('m','Title','Instructions','g','done','Result',NULL,1,2)")
        db.execute("INSERT INTO mission_assignees VALUES ('m',0,'b')")
        db.execute("INSERT INTO mission_runs VALUES ('mr','m','b','run','chief','done','Result',NULL,1,2)")
        db.execute("DELETE FROM bots WHERE id='b'")
        assert db.execute('SELECT chief_bot_id FROM bot_groups').fetchone()[0] is None
        assert db.execute('SELECT count(*) FROM bot_group_members').fetchone()[0]==0
        assert db.execute('SELECT bot_id FROM mission_assignees').fetchone()[0] is None
        row=db.execute('SELECT bot_id,run_id,result FROM mission_runs').fetchone()
        assert row['bot_id'] is None and row['run_id']=='run' and row['result']=='Result'
        assert db.execute('SELECT count(*) FROM runs').fetchone()[0]==0
