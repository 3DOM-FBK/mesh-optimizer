# Use a base image with CUDA support (version 12.8 as required by PartUV) on Ubuntu 24.04
FROM nvidia/cuda:12.8.0-runtime-ubuntu24.04

# Set environment variables to avoid interaction during installation
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1

# Update the system and install necessary system dependencies
# Including wget, git, xz-utils (to extract Blender) and graphics libraries for Blender
RUN apt-get update && apt-get install -y \
    wget \
    git \
    xz-utils \
    software-properties-common \
    libgl1 \
    libxi6 \
    libxrender1 \
    libxxf86vm1 \
    libxfixes3 \
    libxcursor1 \
    libxinerama1 \
    libsm6 \
    libxkbcommon0 \
    libglu1-mesa \
    libxft2 \
    cmake \
    build-essential \
    libboost-all-dev \
    libgmp-dev \
    libmpfr-dev \
    libtbb-dev \
    libeigen3-dev \
    && rm -rf /var/lib/apt/lists/*

# # --- MMG Tools Installation ---
# WORKDIR /opt
# RUN git clone https://github.com/MmgTools/mmg.git && \
#     cd mmg && \
#     mkdir build && \
#     cd build && \
#     cmake .. && \
#     make -j$(nproc) && \
#     make install && \
#     cd ../.. && \
#     rm -rf mmg

# --- CGAL 6.1 Installation from source ---
WORKDIR /opt
RUN wget https://github.com/CGAL/cgal/releases/download/v6.1/CGAL-6.1.tar.xz && \
    tar -xf CGAL-6.1.tar.xz && \
    mkdir CGAL-6.1/build && \
    cd CGAL-6.1/build && \
    cmake .. && \
    make -j$(nproc) && \
    make install && \
    cd ../.. && \
    rm -rf CGAL-6.1 CGAL-6.1.tar.xz

# Install Python 3.11 (required by PartUV)
RUN add-apt-repository ppa:deadsnakes/ppa && \
    apt-get update && \
    apt-get install -y python3.11 python3.11-distutils python3.11-dev python3.11-venv && \
    rm -rf /var/lib/apt/lists/*

# Install pip for Python 3.11
RUN wget https://bootstrap.pypa.io/get-pip.py && \
    python3.11 get-pip.py && \
    rm get-pip.py

# --- Blender 5.0 Installation ---
WORKDIR /opt
# Download and extract Blender 5.0
RUN wget https://download.blender.org/release/Blender5.0/blender-5.0.0-linux-x64.tar.xz && \
    tar -xf blender-5.0.0-linux-x64.tar.xz && \
    rm blender-5.0.0-linux-x64.tar.xz && \
    mv blender-5.0.0-linux-x64 blender

# Add Blender to PATH
ENV PATH="/opt/blender:$PATH"

# Install gmsh in Blender's Python environment
RUN /opt/blender/*/python/bin/python3* -m ensurepip && \
    /opt/blender/*/python/bin/python3* -m pip install gmsh opencv-python

# --- PartUV Installation ---
WORKDIR /workspace

# Create a virtual environment for PartUV to isolate dependencies
RUN python3.11 -m venv /opt/partuv_env
ENV PATH="/opt/partuv_env/bin:$PATH"

# Install PyTorch 2.7.1 with CUDA 12.8 support and torch-scatter
# Note: Wheel URLs are taken from PartUV documentation
RUN pip install --upgrade pip && \
    pip install torch==2.7.1 --index-url https://download.pytorch.org/whl/cu128 && \
    pip install torch-scatter -f https://data.pyg.org/whl/torch-2.7.1+cu128.html

# Clone the PartUV repository
RUN git clone https://github.com/EricWang12/PartUV.git

WORKDIR /workspace/PartUV

# Install requirements and the PartUV package
# Modify requirements.txt to enforce specific versions
RUN sed -i 's/^trimesh.*/trimesh<4.0/' requirements.txt && \
    pip install -r requirements.txt

RUN pip install partuv

RUN pip uninstall -y numpy && \
    pip install "numpy<2.0"

WORKDIR /app
COPY main.py .
COPY pipeline ./pipeline
COPY config/config_partuv.yaml ./config/config_partuv.yaml
COPY c++/cgal/build/remesh /opt

# Default command
ENTRYPOINT [ "python3", "main.py" ]
