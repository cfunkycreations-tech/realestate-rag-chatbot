import asyncio
import json

import pytest

import app as service
from funkbot.redaction import SlidingRedactor


def test_saved_and_generic_secrets_at_all_chunk_boundaries():
    secret = 'custom-secret-without-standard-prefix'
    text = f'Before {secret} and sk-1234567890abcdefghijkl plus Bearer abcdefghijklmnop.END after.'
    for width in range(1, len(text) + 1):
        filter_ = SlidingRedactor([secret])
        output = ''.join(filter_.feed(text[i:i+width]) for i in range(0, len(text), width)) + filter_.finish()
        assert secret not in output
        assert 'sk-1234567890abcdefghijkl' not in output
        assert 'Bearer abcdefghijklmnop.END' not in output
        assert output == 'Before [redacted] and [redacted] plus [redacted] after.'


def test_known_key_crossing_safe_boundary_never_leaks():
    # A key can begin before the safe-cut boundary and finish after it.
    secret = 'ABCDEFGH1234567890'
    redactor = SlidingRedactor([secret])
    emitted = redactor.feed('x' * 40 + secret + 'z' * 8)
    emitted += redactor.feed('z' * 50) + redactor.finish()
    assert secret not in emitted
    assert emitted == 'x' * 40 + '[redacted]' + 'z' * 58


def test_redaction_rejects_unbounded_ambiguous_token():
    redactor = SlidingRedactor([])
    with pytest.raises(ValueError):
        redactor.feed('Bearer ' + 'a' * 131072)


@pytest.mark.asyncio
async def test_run_streams_before_provider_finishes(monkeypatch):
    from test_app import create_test_bot
    bot = create_test_bot()
    service.set_config('profiles', json.dumps({'smart':[{'gateway':'omniroute','model':'model'}]}))
    waiting, proceed = asyncio.Event(), asyncio.Event()

    class Stream:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        def raise_for_status(self): pass
        async def aiter_lines(self):
            yield 'data: ' + json.dumps({'choices':[{'delta':{'content':'A sufficiently long first chunk of helpful text. '}}]})
            waiting.set()
            await proceed.wait()
            yield 'data: ' + json.dumps({'choices':[{'delta':{'content':'A second chunk.'}}]})
            yield 'data: [DONE]'

    class Client:
        def __init__(self, *args, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        def stream(self, *args, **kwargs): return Stream()

    monkeypatch.setattr(service.httpx, 'AsyncClient', Client)
    job = {'events':[], 'done':False}
    task = asyncio.create_task(service.run_chat(job, bot, [], 'smart'))
    await asyncio.wait_for(waiting.wait(), 2)
    assert any(e['type'] == 'delta' for e in job['events'])
    assert not job['done']
    proceed.set()
    await asyncio.wait_for(task, 2)
    assert job['events'][-1]['type'] == 'done'


@pytest.mark.asyncio
async def test_run_never_emits_split_saved_key(monkeypatch):
    from test_app import create_test_bot, FakeClient, FakeStream
    bot = create_test_bot()
    secret = 'opaque-private-gateway-secret-1234'
    settings = json.loads(service.config('gateways'))
    settings['omniroute']['key'] = service.cipher.encrypt(secret.encode()).decode()
    service.set_config('gateways', json.dumps(settings))
    service.set_config('profiles', json.dumps({'smart':[{'gateway':'omniroute','model':'model'}]}))
    chunks = ['A long enough introduction to stream first. ' + secret[:18], secret[18:] + ' and a closing sentence.']
    FakeClient.responses = [FakeStream(200, [
        *['data: ' + json.dumps({'choices':[{'delta':{'content':chunk}}]}) for chunk in chunks],
        'data: [DONE]'])]
    monkeypatch.setattr(service.httpx, 'AsyncClient', FakeClient)
    job = {'events': [], 'done': False}
    await service.run_chat(job, bot, [], 'smart')
    output = ''.join(item.get('content','') for item in job['events'])
    assert secret not in output and '[redacted]' in output
    with service.db() as connection:
        assert secret not in connection.execute('SELECT content FROM messages').fetchone()[0]


def test_overlapping_known_secrets_do_not_split_after_cut_moves():
    # The second match moves the cut into the first match; both must be held.
    redactor = SlidingRedactor(['ABCDEF', 'DEF123456789'])
    output = redactor.feed('x' * 30 + 'ABCDEF123456789' + 'y' * 7)
    output += redactor.feed('z' * 30) + redactor.finish()
    assert output == 'x' * 30 + '[redacted]' + 'y' * 7 + 'z' * 30


def test_seeded_stream_chunkings_match_full_text_redaction():
    import random
    import string
    from funkbot.redaction import redact_text

    randomizer = random.Random(1542)
    for _ in range(500):
        secrets = [''.join(randomizer.choice('abc123') for _ in range(randomizer.randint(2,20))) for _ in range(randomizer.randrange(0,4))]
        parts = [''.join(randomizer.choice('abcdef 123-') for _ in range(randomizer.randrange(0,25))) for _ in range(6)]
        candidates = secrets + [
            'sk-' + ''.join(randomizer.choice(string.ascii_letters + string.digits) for _ in range(20)),
            'Bearer ' + ''.join(randomizer.choice(string.ascii_letters) for _ in range(20)),
        ]
        for _ in range(randomizer.randrange(1,4)):
            parts.insert(randomizer.randrange(len(parts)+1),randomizer.choice(candidates))
        text = ' '.join(parts)
        redactor = SlidingRedactor(secrets)
        output = ''
        index = 0
        while index < len(text):
            width = randomizer.randint(1,30)
            output += redactor.feed(text[index:index+width])
            index += width
        assert output + redactor.finish() == redact_text(text, secrets)
