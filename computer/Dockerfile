FROM python:3.12-slim
# The desktop stays inside the network-disabled container; no VNC port is exposed.
RUN apt-get update && apt-get install -y --no-install-recommends xvfb x11-utils xdotool imagemagick openbox chromium && rm -rf /var/lib/apt/lists/*
COPY computer/worker.py /worker.py
COPY backend/funkbot/computer_snapshot.py /computer_snapshot.py
CMD ["python", "-u", "/worker.py"]
