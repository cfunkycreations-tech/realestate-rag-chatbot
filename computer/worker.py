"""One request per container lifetime. No network, credentials or host mounts.

The parent handles only the root-owned control socket. The command runs as a
separate unprivileged UID. Exiting PID 1 makes the container runtime destroy
all descendants, including processes that detached from the shell.
"""
import json
import os
import resource
import signal
import socket
import subprocess
import tempfile

CONTROL = '/control/computer.sock'
MAX_REQUEST = 100000
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


def execute(command):
    # File-backed output avoids unbounded Python buffering, and is capped by
    # both RLIMIT_FSIZE and the container's bounded /tmp tmpfs.
    with tempfile.TemporaryFile(dir=TEMP) as output:
        process = subprocess.Popen(['/bin/sh', '-c', command], cwd=WORKSPACE,
            stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT,
            env={'PATH':'/usr/local/bin:/usr/bin:/bin', 'HOME':'/workspace', 'TMPDIR':'/tmp'},
            close_fds=True, start_new_session=True, preexec_fn=drop_privileges)
        timed_out = False
        try:
            code = process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            timed_out = True
            try: os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError: pass
            code = process.wait()
        output.seek(0)
        data = output.read(MAX_OUTPUT + 1)
        return {'output':data[:MAX_OUTPUT].decode('utf-8', errors='replace'),
                'truncated':len(data) > MAX_OUTPUT, 'exit_code':code, 'timed_out':timed_out}


def main():
    os.makedirs('/control', mode=0o700, exist_ok=True)
    os.chmod('/control', 0o700)
    try: os.unlink(CONTROL)
    except FileNotFoundError: pass
    server=socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(CONTROL)
    os.chmod(CONTROL, 0o600)
    server.listen(1)
    while True:
        conn, _ = server.accept()
        with conn:
            conn.settimeout(5)
            try:
                data=b''
                while b'\n' not in data and len(data)<=MAX_REQUEST:
                    chunk=conn.recv(min(4096,MAX_REQUEST+1-len(data)))
                    if not chunk: break
                    data+=chunk
                if len(data)>MAX_REQUEST or not data.endswith(b'\n'): continue
                request=json.loads(data)
                if not isinstance(request,dict) or set(request)!={'command'} or not isinstance(request['command'],str) or not 1<=len(request['command'])<=8000 or '\x00' in request['command']:
                    continue
            except (ValueError, OSError, TimeoutError):
                continue
            try:
                result=execute(request['command'])
                conn.sendall(json.dumps(result,ensure_ascii=True).encode()+b'\n')
            except Exception:
                try: conn.sendall(b'{"error":"Computer execution failed."}\n')
                except OSError: pass
            # A new container provides a clean workspace and kills detached jobs.
            return


if __name__ == '__main__': main()
