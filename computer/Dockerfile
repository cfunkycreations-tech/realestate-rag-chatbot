FROM python:3.12-slim
COPY computer/worker.py /worker.py
COPY backend/funkbot/computer_snapshot.py /computer_snapshot.py
CMD ["python", "-u", "/worker.py"]
