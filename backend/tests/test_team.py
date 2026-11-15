import io
import time
from fastapi.testclient import TestClient
from PIL import Image
import app as service
from funkbot.events import append_event
from test_app import setup
from test_vault import archive, png


def test_overview_uses_real_events_and_filters_bot():
    with TestClient(service.app) as client:
        assert client.get('/api/team/overview?day_start=0').status_code == 401
        setup(client)
        a=client.post('/api/bots',json={'name':'A'}).json()['id']
        b=client.post('/api/bots',json={'name':'B'}).json()['id']
        start=time.time()-5
        with service.db() as c:
            append_event(c,a,None,'run.started',{'status':'running'})
            append_event(c,b,None,'bot.state_changed',{'state':'working'})
        data=client.get('/api/team/overview',params={'day_start':start,'bot_id':a}).json()
        assert data['bots']==2 and data['runs_today']==1 and data['last_activity']>=start
        assert len(data['events'])==1 and data['events'][0]['bot_id']==a
        assert data['states'][b]=='working'
        assert client.get('/api/team/overview',params={'day_start':time.time()+20}).json()['runs_today']==0


def test_banner_is_private_validated_and_removable():
    image=io.BytesIO(); Image.new('RGB',(12,5),'purple').save(image,'JPEG')
    with TestClient(service.app) as client:
        assert client.get('/api/settings/banner').status_code==401
        setup(client)
        assert client.get('/api/settings/banner').status_code==404
        assert client.put('/api/settings/banner',files={'file':('fake.png',b'bad','image/png')}).status_code==400
        assert client.put('/api/settings/banner',files={'file':('banner.jpg',image.getvalue(),'image/jpeg')}).status_code==200
        result=client.get('/api/settings/banner')
        assert result.content.startswith(b'\x89PNG') and result.headers['cache-control']=='private, no-store'
        assert client.delete('/api/settings/banner').status_code==200
        assert client.get('/api/settings/banner').status_code==404


def test_collection_tag_added_at_import():
    with TestClient(service.app) as client:
        setup(client)
        response=client.post('/api/vault/import',data={'collection':'Space'},files={'file':('a.zip',archive([('a.png',png('Art'))]),'application/zip')})
        assert response.json()['added']==1
        bot=client.post('/api/bots',json={'name':'Bot'}).json()
        assert bot['character']['tags']==['design','cheerful','Space']


def test_roster_supports_more_than_fifty_bots():
    with TestClient(service.app) as client:
        setup(client)
        with service.db() as c:
            for i in range(50):
                c.execute('INSERT INTO bots VALUES (?,?,?,?,?,?,?,?)', (str(i),f'Bot {i}','Role','Instructions','mint','round','smart',i))
        assert client.post('/api/bots',json={'name':'Bot 51'}).status_code==200
        assert len(client.get('/api/bots').json())==51


def test_banner_placement_private_validated_and_persistent():
    with TestClient(service.app) as client:
        assert client.get('/api/settings/banner-placement').status_code == 401
        assert client.put('/api/settings/banner-placement', json={'x':10}).status_code == 401
        setup(client)
        assert client.get('/api/settings/banner-placement').json() == {'x':50,'y':50,'zoom':1}
        placement = {'x':13,'y':84,'zoom':2.3}
        assert client.put('/api/settings/banner-placement', json=placement).json() == placement
        assert client.put('/api/settings/banner-placement', json={'x':-1,'y':50,'zoom':1}).status_code == 422
        assert client.put('/api/settings/banner-placement', json={'x':50,'y':50,'zoom':4}).status_code == 422
        service.init_db()
        assert client.get('/api/settings/banner-placement').json() == placement
