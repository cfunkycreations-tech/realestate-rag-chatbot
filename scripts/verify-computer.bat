@echo off
setlocal EnableExtensions
cd /d "%~dp0.."
set "LOG=%CD%\computer-verification.txt"
set "PROJECT=funkverify%RANDOM%%RANDOM%"
set "VERIFY_BAT=%~f0"
set "VERIFY_PROBE=%TEMP%\%PROJECT%-probe.py"
>"%LOG%" echo Agent Computer Docker verification
>>"%LOG%" echo Project: %PROJECT%
>>"%LOG%" echo Started: %DATE% %TIME%
echo Writing results to "%LOG%". This uses a disposable Compose project.
call :run docker version || goto fail
call :run docker compose version || goto fail
call :run docker compose -p %PROJECT% --profile computer build computer backend || goto fail
call :run docker compose -p %PROJECT% --profile computer up -d --no-deps computer || goto fail
powershell -NoProfile -NonInteractive -Command "$t=Get-Content -Raw -LiteralPath $env:VERIFY_BAT; $p=[regex]::Split($t,'(?m)^:PYTHON_PROBE\r?$',2); if($p.Count -ne 2){exit 1}; [IO.File]::WriteAllText($env:VERIFY_PROBE,$p[1],[Text.UTF8Encoding]::new($false))" >>"%LOG%" 2>&1 || goto fail
call :run docker compose -p %PROJECT% --profile computer run --rm --no-deps -T -v "%VERIFY_PROBE%:/verification/probe.py:ro" backend python /verification/probe.py || goto fail
>>"%LOG%" echo RESULT: PASS
set "RESULT=0"
goto cleanup
:fail
>>"%LOG%" echo RESULT: FAIL - see command and output above.
set "RESULT=1"
:cleanup
>>"%LOG%" echo Cleanup: stopping disposable project. No production volumes are touched.
docker compose -p %PROJECT% --profile computer down --remove-orphans >>"%LOG%" 2>&1
for %%V in (computer_control funk_data) do docker volume rm %PROJECT%_%%V >>"%LOG%" 2>&1
if exist "%VERIFY_PROBE%" del "%VERIFY_PROBE%"
echo Finished. Results: "%LOG%"
exit /b %RESULT%
:run
>>"%LOG%" echo.
>>"%LOG%" echo ^> %*
%* >>"%LOG%" 2>&1
exit /b %ERRORLEVEL%
:PYTHON_PROBE
import base64
import json
import socket
import time

SOCKET = '/computer-control/computer.sock'
EMPTY = {'dirs': [], 'files': {}}

def connect():
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(10)
        try:
            sock.connect(SOCKET)
            stream = sock.makefile('rb')
            if stream.readline() == b'{"ready":1}\n':
                return sock, stream
        except (OSError, TimeoutError):
            pass
        sock.close()
        time.sleep(.25)
    raise RuntimeError('Worker did not become ready')

def command(cmd, workspace, desktop=False):
    sock, stream = connect()
    request = {'command': cmd, 'workspace': workspace}
    if desktop:
        request['desktop'] = True
    sock.sendall(json.dumps(request).encode() + b'\n')
    sock.settimeout(45)
    frames = 0
    while True:
        line = stream.readline(5 * 1024 * 1024)
        if not line:
            raise RuntimeError('Worker disconnected before result')
        result = json.loads(line)
        if 'frame' in result:
            image = base64.b64decode(result['frame'], validate=True)
            assert image.startswith(b'\x89PNG\r\n\x1a\n') and len(image) <= 1024 * 1024
            frames += 1
            continue
        break
    sock.close()
    if 'error' in result:
        raise RuntimeError(result['error'])
    assert result['exit_code'] == 0 and not result['timed_out'], result
    print('OUTPUT:', result['output'])
    print('DESKTOP FRAMES:', frames)
    if desktop:
        assert frames > 0, 'The real desktop did not produce a PNG frame'
    return result['workspace'], result['output']

print('Running real worker, desktop, sandbox and workspace checks')
workspace, output = command("printf 'UID='; id -u; if test -r /control/computer.sock; then echo CONTROL_READABLE; else echo CONTROL_PROTECTED; fi; if touch /root-write-test 2>/dev/null; then echo ROOT_WRITABLE; else echo ROOT_READONLY; fi; cat /proc/net/route; command -v chromium; command -v Xvfb; printf computer-fixture > proof.txt; sleep 4", EMPTY, True)
assert 'UID=65534' in output and 'CONTROL_PROTECTED' in output and 'ROOT_READONLY' in output
routes = [line for line in output.splitlines() if '\t00000000\t' in line]
assert not routes, 'A default IPv4 route was present: ' + repr(routes)
assert 'proof.txt' in workspace['files']
_, output = command('cat proof.txt', workspace)
assert 'computer-fixture' in output
print('PASS: worker ran unprivileged, control/socket and root were protected, no default IPv4 route, desktop frame arrived and workspace restored')

print('Checking a persistent real Playwright session and exclusive takeover')
sock, stream = connect()
sock.settimeout(50)
sock.sendall(json.dumps({'mode':'session','workspace':workspace}).encode()+b'\n')
def receive():
    while True:
        line=stream.readline(5*1024*1024)
        if not line: raise RuntimeError('Session disconnected unexpectedly')
        msg=json.loads(line)
        if set(msg)=={'frame'}: continue
        return msg
def send(value): sock.sendall(json.dumps(value).encode()+b'\n')
assert receive()=={'session':'started'}, 'Playwright Chromium did not start'
send({'type':'action','id':'one','action':{'type':'open_url','url':'about:blank'}})
response=receive();assert response.get('ok') and response.get('frame'),response
send({'type':'takeover','id':'take','enabled':True});assert receive().get('takeover') is True
send({'type':'action','id':'blocked','action':{'type':'screenshot'}});assert receive().get('ok') is False
send({'type':'takeover','id':'back','enabled':False});assert receive().get('takeover') is False
send({'type':'action','id':'two','action':{'type':'screenshot'}});assert receive().get('ok') is True
send({'type':'close'});result=receive();assert result.get('session')=='ended',result
sock.close()
print('PASS: real Playwright session persisted across actions, captured screenshots and blocked Bot actions during takeover')

print('Checking the out-of-band worker kill socket')
sock, stream=connect();sock.sendall(json.dumps({'command':'sleep 20','workspace':EMPTY}).encode()+b'\n');time.sleep(1)
kill=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);kill.settimeout(5);kill.connect('/computer-control/computer-kill.sock');kill.sendall(b'kill\n');kill.close()
sock.settimeout(10)
try: ended=stream.readline()
except (OSError,ConnectionError): ended=b''
assert not ended, 'Worker returned a result instead of dying after kill'
sock.close()
_,output=command('echo RESTARTED',EMPTY)
assert 'RESTARTED' in output
print('PASS: kill socket interrupted the worker and Compose restarted it')
