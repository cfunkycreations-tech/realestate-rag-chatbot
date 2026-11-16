"""Disposable UI-test backend; never use with a real workspace or worker.

Requires an empty FUNK_DATA_DIR and an explicit mock-worker Unix socket.
"""
import os
import sys
from pathlib import Path

root=Path(__file__).resolve().parents[1]
data=os.environ.get('FUNK_DATA_DIR')
socket=os.environ.get('COMPUTER_TEST_SOCKET')
if not data or not socket or os.environ.get('FUNK_COMPUTER_ENABLED')!='1':
    raise SystemExit('Set FUNK_DATA_DIR, COMPUTER_TEST_SOCKET and FUNK_COMPUTER_ENABLED=1 for a disposable test.')
data_path=Path(data).resolve()
if data_path.exists() and (not data_path.is_dir() or any(data_path.iterdir())):
    raise SystemExit('FUNK_DATA_DIR must be a new or empty disposable directory.')
data_path.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(root/'backend'))
from funkbot import computer
computer.SOCKET=socket
import app
import uvicorn
uvicorn.run(app.app,host='0.0.0.0',port=int(os.getenv('COMPUTER_TEST_PORT','8094')))
