"""One command per container lifetime; only data snapshots cross the boundary."""
import json
import os
import resource
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


def execute(command):
    with tempfile.TemporaryFile(dir=TEMP) as output:
        process=subprocess.Popen(['/bin/sh','-c',command],cwd=WORKSPACE,
            stdin=subprocess.DEVNULL,stdout=output,stderr=subprocess.STDOUT,
            env={'PATH':'/usr/local/bin:/usr/bin:/bin','HOME':'/workspace','TMPDIR':'/tmp'},
            close_fds=True,start_new_session=True,preexec_fn=drop_privileges)
        timed_out=False
        try: code=process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            timed_out=True
            try: os.killpg(process.pid,signal.SIGKILL)
            except ProcessLookupError: pass
            code=process.wait()
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
                if not isinstance(request,dict) or set(request)!={'command','workspace'} or not isinstance(request['command'],str) or not 1<=len(request['command'])<=8000 or '\x00' in request['command']: continue
                snapshot.validate(request['workspace'])
            except (ValueError,OSError,TimeoutError,RecursionError): continue
            try:
                restore_as_user(request['workspace'])
                result=execute(request['command'])
                stop_unprivileged_processes()
                result['workspace']=collect_as_user()
                conn.sendall(json.dumps(result,ensure_ascii=True,separators=(',',':')).encode()+b'\n')
            except Exception:
                try: conn.sendall(b'{"error":"Computer execution or workspace save failed; previous workspace retained. Command may have run."}\n')
                except OSError: pass
            # PID 1 exits: Docker must destroy the entire process namespace.
            return


if __name__=='__main__': main()
