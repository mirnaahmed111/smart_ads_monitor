FROM python:3.10-slim

WORKDIR /app

# Install system libraries required by OpenCV, pygame, PyAudio
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxrender1 \
    libxext6 \
    portaudio19-dev \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy your project files
COPY . .

# Install Python dependencies for ARM
RUN pip install --no-cache-dir -r requirements.txt

CMD ["python", "main.py"]

