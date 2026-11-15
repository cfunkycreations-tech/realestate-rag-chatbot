import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
import app as service
from funkbot.tool_policy import WebPolicy
from test_app import setup


def test_web_policy_api_is_private_default_deny_and_persistent():
    with TestClient(service.app) as c:
        assert c.get('/api/settings/web-policy').status_code==401
        assert c.put('/api/settings/web-policy',json={'allow':['example.com'],'deny':[]}).status_code==401
        setup(c)
        assert c.get('/api/settings/web-policy').json()=={'allow':[],'deny':[]}
        data={'allow':['.Example.com','EXAMPLE.com','.example.com'],'deny':['private.example.com']}
        assert c.put('/api/settings/web-policy',json=data).json()=={'allow':['.example.com','example.com'],'deny':['private.example.com']}
        service.init_db()
        assert c.get('/api/settings/web-policy').json()=={'allow':['.example.com','example.com'],'deny':['private.example.com']}


@pytest.mark.parametrize('host',['*','*.example.com','https://example.com/path','example.com:443','127.0.0.1','::1','169.254.169.254','host','bad..name','-bad.example','example.com/secret',' host.com'])
def test_invalid_policy_entries_are_rejected(host):
    with pytest.raises(ValidationError): WebPolicy(allow=[host])
