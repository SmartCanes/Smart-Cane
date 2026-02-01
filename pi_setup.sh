#!/bin/bash
set -e

echo "=== Smart Cane Full Setup (Raspberry Pi / Python 3.11) ==="

# 1️⃣ Update system
sudo apt update
sudo apt upgrade -y

# 2️⃣ Install system dependencies for Python, OpenCV, PyTorch
sudo apt install -y build-essential cmake libblas-dev liblapack-dev \
    libjpeg-dev libcap-dev libopenblas-dev libssl-dev zlib1g-dev \
    libbz2-dev libreadline-dev libsqlite3-dev libncursesw5-dev \
    xz-utils tk-dev libffi-dev liblzma-dev wget curl git

# 3️⃣ Install Picamera2, libcamera, PulseAudio, Bluetooth, espeak, network manager
sudo apt install -y python3-pip python3-venv python3-opencv python3-picamera2 \
    libcamera-apps libcamera-tools pulseaudio pulseaudio-utils bluez \
    libasound2-dev espeak network-manager

# 4️⃣ Install Python 3.11 (via pyenv recommended) if not installed
# (skip if already installed)

# 5️⃣ Create venv using Python 3.11
python3.11 -m venv --system-site-packages ~/smartcane/.venv

# 6️⃣ Activate venv
source ~/smartcane/.venv/bin/activate

# 7️⃣ Upgrade pip
pip install --upgrade pip setuptools wheel

# 8️⃣ Install ARM-compatible PyTorch
# Install PyTorch + Torchaudio + Torchvision from official ARM64 CPU wheel
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu

# Install the rest from mirror
pip install numpy opencv-python pillow scipy ultralytics picamera2 -i https://pypi.tuna.tsinghua.edu.cn/simple/


# 🔟 Deactivate venv
deactivate

echo "✅ Setup complete!"
