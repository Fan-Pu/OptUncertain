# Matterport3DSimulator (Ubuntu 22.04 + Python 3.10)
# GPU support is provided at runtime by nvidia-container-toolkit (--gpus all).
# Base: CUDA devel + cuDNN on Ubuntu 22.04.
FROM nvidia/cuda:11.8.0-cudnn8-devel-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
SHELL ["/bin/bash", "-lc"]

# -------------------- Base deps --------------------
# Notes:
# - Python 3.10 is Ubuntu 22.04 default.
# - We build OpenCV from source with Qt5 + OpenGL enabled (this fixes cv2 WINDOW_OPENGL).
# - jsoncpp + glm are required by Matterport3DSimulator.
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget curl git ca-certificates pkg-config \
    build-essential \
    cmake \
    doxygen \
    libjsoncpp-dev libepoxy-dev libglm-dev \
    libosmesa6 libosmesa6-dev \
    libgl1-mesa-dev libglu1-mesa-dev mesa-common-dev freeglut3-dev mesa-utils \
    libglew-dev \
    libgtk-3-dev \
    libavcodec-dev libavformat-dev libswscale-dev libv4l-dev \
    libjpeg-dev libpng-dev libtiff-dev \
    python3.10 python3.10-dev python3-pip python3-setuptools \
    qtbase5-dev qttools5-dev qttools5-dev-tools libqt5opengl5-dev \
	ninja-build \
 && rm -rf /var/lib/apt/lists/*

# Make sure pip is up-to-date for Python 3.10
RUN python3 -m pip install --no-cache-dir -U pip wheel setuptools

# -------------------- Python packages --------------------
# Pin numpy<2 (opencv + many binary wheels still expect NumPy 1.x ABI)
RUN python3 -m pip install --no-cache-dir \
    "numpy<2" pandas networkx debugpy pillow matplotlib

# -------------------- Build OpenCV with Qt5 + OpenGL --------------------
# IMPORTANT:
# - Do NOT install apt's python3-opencv or pip opencv-python.
# - We build OpenCV from source, and enable Qt OpenGL support.
ARG OPENCV_VERSION=4.5.5

RUN git clone --branch ${OPENCV_VERSION} --depth 1 https://github.com/opencv/opencv.git /tmp/opencv \
 && git clone --branch ${OPENCV_VERSION} --depth 1 https://github.com/opencv/opencv_contrib.git /tmp/opencv_contrib \
 && rm -rf /tmp/opencv/build \
 && mkdir -p /tmp/opencv/build \
 && cd /tmp/opencv/build \
 && cmake .. -G "Unix Makefiles" \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX=/usr/local \
    -DOPENCV_EXTRA_MODULES_PATH=/tmp/opencv_contrib/modules \
    -DWITH_OPENGL=ON \
    -DWITH_QT=ON \
    -DWITH_GTK=OFF \
    -DBUILD_opencv_python3=ON \
    -DBUILD_opencv_python2=OFF \
	-DPYTHON3_EXECUTABLE=/usr/bin/python3.10 \
    -DPYTHON3_INCLUDE_DIR=/usr/include/python3.10 \
    -DBUILD_TESTS=OFF \
    -DBUILD_PERF_TESTS=OFF \
    -DBUILD_EXAMPLES=OFF \
 && make -j"$(nproc)" \
 && make install \
 && ldconfig \
 && rm -rf /tmp/opencv /tmp/opencv_contrib

# Sanity check during build (Qt OpenGL support is what matters here)
RUN python3 - <<'PY'
import cv2
info = cv2.getBuildInformation().splitlines()
print("OpenCV:", cv2.__version__)
print("cv2 path:", cv2.__file__)
gui = [l for l in info if "GUI:" in l]
qtgl = [l for l in info if "QT OpenGL support" in l]
ogl = [l for l in info if "OpenGL support" in l]
if gui: print(gui[0])
if qtgl: print(qtgl[0])
elif ogl: print(ogl[0])
PY

# Matterport3DSimulator build output is expected to be mounted to this path at runtime.
ENV PYTHONPATH=/root/mount/Matterport3DSimulator/build

# -------------------- PyTorch (CUDA 11.8 wheels) --------------------
RUN python3 -m pip install --no-cache-dir \
    torch torchvision torchaudio \
    --index-url https://download.pytorch.org/whl/cu118
	
# Qwen2-VL support: install Transformers from source (recommended by Qwen2-VL model card)
RUN python3 -m pip install --no-cache-dir \
    git+https://github.com/huggingface/transformers \
    accelerate sentencepiece tokenizers safetensors
	
RUN python3 -m pip install --no-cache-dir \
    openai