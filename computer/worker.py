"""One command per container lifetime; only data snapshots cross the boundary."""
import base64
import json
import os
import resource
import select
import signal
import socket
import subprocess
import tempfile
import threading
import time

import computer_snapshot as snapshot

CONTROL = '/control/computer.sock'
MAX_REQUEST = snapshot.MAX_JSON + 100000
MAX_OUTPUT = 16384
WORKSPACE = '/workspace'
TEMP = '/tmp'


def drop_privileges():
    os.setgroups([])
    os.setgid(65534)
    os.setuid(65534)
    resource.setrlimit(resource.RLIMIT_FSIZE, (1024 * 1024, 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    resource.setrlimit(resource.RLIMIT_CPU, (25, 25))


def drop_desktop_privileges():
    # Browser/X server need more descriptors and CPU than a short shell.
    # Compose still bounds the complete container's memory, PIDs and CPU.
    os.setgroups([]);os.setgid(65534);os.setuid(65534)
    resource.setrlimit(resource.RLIMIT_FSIZE,(32*1024*1024,32*1024*1024))
    resource.setrlimit(resource.RLIMIT_NOFILE,(256,256))
    resource.setrlimit(resource.RLIMIT_CPU,(120,120))


def restore_as_user(data):
    # Only this child can write the fresh workspace; the server remains root.
    pid=os.fork()
    if pid==0:
        try:
            drop_privileges();snapshot.restore(data,WORKSPACE)
            os._exit(0)
        except BaseException: os._exit(1)
    _,status=os.waitpid(pid,0)
    if not os.WIFEXITED(status) or os.WEXITSTATUS(status)!=0: raise snapshot.SnapshotError('Could not restore workspace.')


def signal_command_processes():
    for sig in (signal.SIGSTOP,signal.SIGKILL):
        try: os.kill(-1,sig)
        except ProcessLookupError: pass  # No descendants remain.


def stop_unprivileged_processes():
    # In the container's private PID namespace, stop then kill every process
    # owned by the command UID, including detached descendants. The helper runs
    # as that UID so kill(-1) cannot signal the root server. Never run this
    # function outside the intended isolated container PID namespace.
    pid=os.fork()
    if pid==0:
        try:
            drop_privileges()
            signal_command_processes()
            os._exit(0)
        except BaseException: os._exit(1)
    _,status=os.waitpid(pid,0)
    if not os.WIFEXITED(status) or os.WEXITSTATUS(status)!=0: raise RuntimeError('Process cleanup failed.')
    # Refuse to save if any live command-UID process remains. A zombie cannot
    # modify files; PID 1/container exit will reap it.
    deadline=time.monotonic()+2
    while True:
        try:
            while os.waitpid(-1,os.WNOHANG)[0]: pass
        except ChildProcessError: pass
        live=[]
        for name in os.listdir('/proc'):
            if not name.isdigit(): continue
            try:
                with open('/proc/'+name+'/status') as f: status_text=f.read(8192)
                fields=dict(line.split(':',1) for line in status_text.splitlines() if ':' in line)
                if fields['Uid'].split()[0]=='65534' and not fields['State'].strip().startswith('Z'): live.append(name)
            except FileNotFoundError: continue
        if not live: return
        if time.monotonic()>=deadline: raise RuntimeError('Command descendants still running.')
        time.sleep(.02)


def collect_as_user():
    read_fd,write_fd=os.pipe()
    pid=os.fork()
    if pid==0:
        os.close(read_fd)
        try:
            drop_privileges()
            data=json.dumps(snapshot.collect(WORKSPACE),separators=(',',':')).encode()
            with os.fdopen(write_fd,'wb') as output: output.write(data)
            os._exit(0)
        except BaseException: os._exit(1)
    os.close(write_fd)
    try:
        with os.fdopen(read_fd,'rb') as source: data=source.read(snapshot.MAX_JSON+1)
        _,status=os.waitpid(pid,0)
    except BaseException:
        os.kill(pid,signal.SIGKILL);os.waitpid(pid,0);raise
    if not os.WIFEXITED(status) or os.WEXITSTATUS(status)!=0 or len(data)>snapshot.MAX_JSON:
        raise snapshot.SnapshotError('Could not save workspace.')
    return snapshot.validate(json.loads(data))


class CommandCancelled(Exception): pass


def peer_disconnected(conn):
    if conn is None: return False
    try:
        ready,_,_=select.select([conn],[],[],0)
        # Any additional input violates the one-request protocol. EOF means
        # the backend cancelled or disappeared; both must stop the command.
        if not ready: return False
        conn.recv(1,socket.MSG_PEEK)
        return True
    except (OSError,ValueError): return True


def desktop_input(event):
    """Only fixed xdotool arguments are accepted; never invoke a shell."""
    if not isinstance(event,dict): return
    kind=event.get('type')
    if kind=='click' and set(event)=={'type','x','y','button'}:
        x,y,button=event['x'],event['y'],event['button']
        if type(x) is not int or type(y) is not int or type(button) is not int or not (0<=x<1024 and 0<=y<768 and button in (1,2,3)): return
        args=['mousemove','--sync',str(x),str(y),'click',str(button)]
    elif kind=='key' and set(event)=={'type','key'} and event['key'] in ('Return','Tab','Escape','BackSpace','Delete','Left','Right','Up','Down','Home','End','Page_Up','Page_Down','ctrl+l','ctrl+a','ctrl+c','ctrl+v'):
        args=['key',event['key']]
    elif kind=='text' and set(event)=={'type','text'} and isinstance(event['text'],str) and 1<=len(event['text'])<=200 and all(32<=ord(c)<=126 for c in event['text']):
        args=['type','--clearmodifiers','--delay','0','--',event['text']]
    else: return
    try: subprocess.run(['xdotool',*args],env={'DISPLAY':':99','PATH':'/usr/bin:/bin','HOME':'/tmp'},stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,preexec_fn=drop_privileges,timeout=2,check=False)
    except (OSError,subprocess.TimeoutExpired): pass


def desktop_frame():
    # Capture as the same unprivileged user as the display, with no shell.
    env={'DISPLAY':':99','PATH':'/usr/bin:/bin','HOME':'/tmp'}
    try:
        xwd=subprocess.Popen(['xwd','-root','-silent'],env=env,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,preexec_fn=drop_privileges)
        try:
            image=subprocess.run(['convert','xwd:-','png:-'],env=env,stdin=xwd.stdout,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,preexec_fn=drop_privileges,timeout=2,check=False)
        finally:
            xwd.stdout.close()
            try: xwd.wait(timeout=1)
            except subprocess.TimeoutExpired: xwd.kill();xwd.wait()
        if image.returncode==0 and len(image.stdout)<=1024*1024 and image.stdout.startswith(b'\x89PNG\r\n\x1a\n'):
            return image.stdout
    except (OSError,subprocess.TimeoutExpired): pass
    return None


def start_desktop(conn):
    display=subprocess.Popen(['Xvfb',':99','-screen','0','1024x768x24','-nolisten','tcp','-noreset'],cwd=WORKSPACE,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,env={'PATH':'/usr/bin:/bin','HOME':'/tmp'},preexec_fn=drop_desktop_privileges,start_new_session=True)
    env={'DISPLAY':':99','PATH':'/usr/bin:/bin','HOME':'/tmp'}
    for _ in range(30):
        if peer_disconnected(conn): raise CommandCancelled()
        check=subprocess.run(['xdpyinfo'],env=env,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,preexec_fn=drop_privileges,timeout=2,check=False)
        if check.returncode==0: break
        time.sleep(.1)
    else: raise RuntimeError('Virtual display could not start.')
    subprocess.Popen(['openbox'],cwd=WORKSPACE,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,env=env,preexec_fn=drop_desktop_privileges,start_new_session=True)
    return display


def execute(command,conn=None,desktop=False):
    if desktop: start_desktop(conn)
    with tempfile.TemporaryFile(dir=TEMP) as output:
        if peer_disconnected(conn): raise CommandCancelled()
        process=subprocess.Popen(['/bin/sh','-c',command],cwd=WORKSPACE,
            stdin=subprocess.DEVNULL,stdout=output,stderr=subprocess.STDOUT,
            env={'PATH':'/usr/local/bin:/usr/bin:/bin','HOME':'/workspace','TMPDIR':'/tmp',**({'DISPLAY':':99'} if desktop else {})},
            close_fds=True,start_new_session=True,preexec_fn=drop_privileges)
        timed_out=False;cancelled=False;deadline=time.monotonic()+30;next_frame=time.monotonic()+.5;incoming=b''
        while True:
            # Check the connection even if the child exited, so a cancelled
            # caller does not receive or persist a workspace result.
            if desktop and conn:
                ready,_,_=select.select([conn],[],[],0)
                if ready:
                    try: chunk=conn.recv(4096)
                    except OSError: chunk=b''
                    if not chunk: cancelled=True;break
                    incoming+=chunk
                    if len(incoming)>8192: cancelled=True;break
                    while b'\n' in incoming:
                        line,incoming=incoming.split(b'\n',1)
                        try: desktop_input(json.loads(line))
                        except (ValueError,RecursionError): pass
                if time.monotonic()>=next_frame:
                    frame=desktop_frame();next_frame=time.monotonic()+1
                    if frame:
                        try: conn.sendall(json.dumps({'frame':base64.b64encode(frame).decode('ascii')},separators=(',',':')).encode()+b'\n')
                        except OSError: cancelled=True;break
            elif peer_disconnected(conn): cancelled=True;break
            code=process.poll()
            if code is not None: break
            if time.monotonic()>=deadline: timed_out=True;break
            time.sleep(.05)
        if timed_out or cancelled:
            try: os.killpg(process.pid,signal.SIGKILL)
            except ProcessLookupError: pass
            try: code=process.wait(timeout=2)
            except subprocess.TimeoutExpired: raise CommandCancelled()  # PID 1 exit tears down the container.
        if cancelled: raise CommandCancelled()
        output.seek(0);data=output.read(MAX_OUTPUT+1)
        return {'output':data[:MAX_OUTPUT].decode('utf-8',errors='replace'),
                'truncated':len(data)>MAX_OUTPUT,'exit_code':code,'timed_out':timed_out}




def start_browser_proxy():
    """Bridge loopback to the backend in a separate root helper process.

    The worker remains single-threaded so its privilege-dropping forks cannot
    deadlock on locks held by a vanished thread.
    """
    server=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
    server.bind(('127.0.0.1',0));server.listen(12)
    port=server.getsockname()[1];pid=os.fork()
    if pid:
        server.close();return port,pid
    # Do not leak the worker control connection or listener to this helper.
    keep=server.fileno()
    for name in os.listdir('/proc/self/fd'):
        if name.isdigit() and int(name)>2 and int(name)!=keep:
            try: os.close(int(name))
            except OSError: pass
    slots=threading.BoundedSemaphore(12)
    def forward(client):
        upstream=None
        try:
            upstream=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);upstream.settimeout(5)
            upstream.connect('/control/browser-proxy.sock');upstream.settimeout(10);client.settimeout(10)
            total=0;deadline=time.monotonic()+95
            while time.monotonic()<deadline:
                ready,_,_=select.select([client,upstream],[],[],1)
                for src in ready:
                    data=src.recv(32768)
                    if not data: return
                    total+=len(data)
                    if total>40*1024*1024: return
                    (upstream if src is client else client).sendall(data)
        except OSError: pass
        finally:
            client.close()
            if upstream: upstream.close()
            slots.release()
    try:
        while True:
            client,_=server.accept()
            if not slots.acquire(blocking=False): client.close();continue
            threading.Thread(target=forward,args=(client,),daemon=True).start()
    except BaseException: os._exit(1)


def stop_browser_proxy(pid):
    if pid is None: return
    try: os.kill(pid,signal.SIGKILL)
    except ProcessLookupError: pass
    try: os.waitpid(pid,0)
    except ChildProcessError: pass

SESSION_IDLE=120
SESSION_HARD=600


def session_send(conn,body):
    conn.sendall(json.dumps(body,ensure_ascii=True,separators=(',',':')).encode()+b'\n')


def browser_reply(browser,timeout):
    ready,_,_=select.select([browser.stdout],[],[],timeout)
    if not ready: raise RuntimeError('Browser did not respond before its deadline.')
    line=browser.stdout.readline(150000)
    if not line or len(line)>=150000: raise RuntimeError('Browser response is invalid.')
    response=json.loads(line)
    if not isinstance(response,dict) or type(response.get('ok')) is not bool: raise RuntimeError('Browser response is invalid.')
    return response


def serve_session(conn,workspace):
    """Keep one browser and desktop alive across actions, never across clients."""
    browser=None;proxy_pid=None;graceful=False
    try:
        restore_as_user(workspace);start_desktop(conn)
        proxy_port,proxy_pid=start_browser_proxy()
        browser=subprocess.Popen(['python','-u','/session_browser.py'],cwd=WORKSPACE,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,env={'PATH':'/usr/local/bin:/usr/bin:/bin','HOME':'/tmp','TMPDIR':'/tmp','DISPLAY':':99','PYTHONUNBUFFERED':'1','FUNK_BROWSER_PROXY_PORT':str(proxy_port)},preexec_fn=drop_desktop_privileges,start_new_session=True)
        ready,_,_=select.select([browser.stdout],[],[],20)
        if not ready or json.loads(browser.stdout.readline(4096))!={'ready':True}: raise RuntimeError('Browser failed to start.')
        session_send(conn,{'session':'started'})
        start=last_activity=time.monotonic();next_frame=start;incoming=b'';takeover=False
        while True:
            now=time.monotonic()
            if now-start>=SESSION_HARD or now-last_activity>=SESSION_IDLE:
                reason='hard_timeout' if now-start>=SESSION_HARD else 'idle_timeout';graceful=True;break
            ready,_,_=select.select([conn],[],[],.1)
            if ready:
                data=conn.recv(16384)
                if not data: raise CommandCancelled()
                incoming+=data
                if len(incoming)>20000: raise RuntimeError('Session request is too large.')
                while b'\n' in incoming:
                    line,incoming=incoming.split(b'\n',1)
                    message=json.loads(line)
                    if not isinstance(message,dict) or not isinstance(message.get('type'),str): raise RuntimeError('Invalid session request.')
                    kind=message['type'];last_activity=time.monotonic()
                    if kind=='close' and set(message)=={'type'}: reason='closed';graceful=True;break
                    if kind=='takeover' and set(message)=={'type','enabled','id'} and type(message['enabled']) is bool and isinstance(message['id'],str):
                        takeover=message['enabled'];session_send(conn,{'id':message['id'],'ok':True,'takeover':takeover})
                    elif kind=='owner_input' and set(message)=={'type','event'}:
                        if takeover: desktop_input(message['event'])
                    elif kind=='action' and set(message)=={'type','id','action'} and isinstance(message['id'],str) and len(message['id'])<=128:
                        if takeover:
                            session_send(conn,{'id':message['id'],'ok':False,'error':'The owner controls the desktop.'});continue
                        browser.stdin.write(json.dumps(message['action'],ensure_ascii=True).encode()+b'\n');browser.stdin.flush()
                        response=browser_reply(browser,15)
                        frame=desktop_frame()
                        if frame: response['frame']=base64.b64encode(frame).decode('ascii')
                        elif response['ok']: response={'ok':False,'error':'Action may have run, but desktop capture failed; do not retry without review.'}
                        session_send(conn,{'id':message['id'],**response})
                    else: raise RuntimeError('Invalid session request.')
                if graceful: break
            if time.monotonic()>=next_frame:
                frame=desktop_frame();next_frame=time.monotonic()+1
                if frame: session_send(conn,{'frame':base64.b64encode(frame).decode('ascii')})
        stop_unprivileged_processes()
        saved=collect_as_user()
        session_send(conn,{'session':'ended','reason':reason,'workspace':saved})
    except CommandCancelled:
        try: stop_unprivileged_processes()
        except Exception: pass
    except Exception:
        try: session_send(conn,{'error':'Desktop session failed; actions may have run and the previous workspace was retained.'})
        except OSError: pass
    stop_browser_proxy(proxy_pid)
    # PID 1 exits after return; the private namespace is discarded.



def start_kill_switch():
    """Root-only helper asks PID 1 to exit, tearing down the container."""
    path='/control/computer-kill.sock'
    try: os.unlink(path)
    except FileNotFoundError: pass
    server=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);server.bind(path);os.chmod(path,0o600);server.listen(2)
    signal.signal(signal.SIGUSR1,lambda *_:os._exit(137))
    pid=os.fork()
    if pid:
        server.close();return pid
    try:
        while True:
            conn,_=server.accept()
            try:
                with conn:
                    conn.settimeout(2);data=b''
                    while len(data)<5:
                        chunk=conn.recv(5-len(data))
                        if not chunk: break
                        data+=chunk
                    if data==b'kill\n': os.kill(1,signal.SIGUSR1)
            except OSError: continue
    except BaseException: os._exit(1)


def main():
    if os.getpid()!=1: raise RuntimeError('Worker requires a private container PID namespace with Python as PID 1.')
    control_dir=os.path.dirname(CONTROL)
    os.makedirs(control_dir,mode=0o700,exist_ok=True);os.chmod(control_dir,0o700)
    kill_server=start_kill_switch()
    try: os.unlink(CONTROL)
    except FileNotFoundError: pass
    server=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);server.bind(CONTROL)
    os.chmod(CONTROL,0o600);server.listen(1)
    while True:
        conn,_=server.accept()
        with conn:
            conn.settimeout(10)
            try:
                conn.sendall(b'{"ready":1}\n')
                data=b''
                while b'\n' not in data and len(data)<=MAX_REQUEST:
                    chunk=conn.recv(min(65536,MAX_REQUEST+1-len(data)))
                    if not chunk: break
                    data+=chunk
                if len(data)>MAX_REQUEST or not data.endswith(b'\n'): continue
                request=json.loads(data)
                if isinstance(request,dict) and set(request)=={'mode','workspace'} and request['mode']=='session':
                    snapshot.validate(request['workspace'])
                    serve_session(conn,request['workspace'])
                    return
                if not isinstance(request,dict) or set(request) not in ({'command','workspace'},{'command','workspace','desktop'}) or type(request.get('desktop',False)) is not bool or not isinstance(request['command'],str) or not 1<=len(request['command'])<=8000 or '\x00' in request['command']: continue
                snapshot.validate(request['workspace'])
            except (ValueError,OSError,TimeoutError,RecursionError): continue
            try:
                restore_as_user(request['workspace'])
                result=execute(request['command'],conn,request.get('desktop',False))
                stop_unprivileged_processes()
                result['workspace']=collect_as_user()
                conn.sendall(json.dumps(result,ensure_ascii=True,separators=(',',':')).encode()+b'\n')
            except CommandCancelled:
                try: stop_unprivileged_processes()
                except Exception: pass  # Container exit remains the last resort.
            except Exception:
                try: conn.sendall(b'{"error":"Computer execution or workspace save failed; previous workspace retained. Command may have run."}\n')
                except OSError: pass
            # PID 1 exits: Docker must destroy the entire process namespace.
            return


if __name__=='__main__': main()
