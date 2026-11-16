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
    try: subprocess.run(['xdotool',*args],env={'DISPLAY':':99','PATH':'/usr/bin:/bin','HOME':WORKSPACE},stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,preexec_fn=drop_privileges,timeout=2,check=False)
    except (OSError,subprocess.TimeoutExpired): pass


def desktop_frame():
    # Capture as the same unprivileged user as the display, with no shell.
    env={'DISPLAY':':99','PATH':'/usr/bin:/bin','HOME':WORKSPACE}
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


def execute(command,conn=None,desktop=False):
    display=None
    if desktop:
        display=subprocess.Popen(['Xvfb',':99','-screen','0','1024x768x24','-nolisten','tcp','-noreset'],cwd=WORKSPACE,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,env={'PATH':'/usr/bin:/bin','HOME':WORKSPACE},preexec_fn=drop_privileges,start_new_session=True)
        # Wait for the local display before launching the command.
        env={'DISPLAY':':99','PATH':'/usr/bin:/bin','HOME':WORKSPACE}
        for _ in range(30):
            if peer_disconnected(conn): raise CommandCancelled()
            check=subprocess.run(['xdpyinfo'],env=env,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,preexec_fn=drop_privileges,timeout=2,check=False)
            if check.returncode==0: break
            time.sleep(.1)
        else: raise RuntimeError('Virtual display could not start.')
        subprocess.Popen(['openbox'],cwd=WORKSPACE,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,env=env,preexec_fn=drop_privileges,start_new_session=True)
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


def main():
    if os.getpid()!=1: raise RuntimeError('Worker requires a private container PID namespace with Python as PID 1.')
    control_dir=os.path.dirname(CONTROL)
    os.makedirs(control_dir,mode=0o700,exist_ok=True);os.chmod(control_dir,0o700)
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
