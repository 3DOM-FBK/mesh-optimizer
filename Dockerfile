# Usa un'immagine base con supporto CUDA (versione 12.8 come richiesto da PartUV) su Ubuntu 24.04
FROM nvidia/cuda:12.8.0-runtime-ubuntu24.04

# Imposta variabili d'ambiente per evitare interazioni durante l'installazione
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1

# Aggiorna il sistema e installa le dipendenze di sistema necessarie
# Inclusi wget, git, xz-utils (per estrarre Blender) e librerie grafiche per Blender
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

# # --- Installazione di MMG Tools ---
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

# --- Installazione di CGAL 6.1 da sorgente ---
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

# Installa Python 3.11 (richiesto da PartUV)
RUN add-apt-repository ppa:deadsnakes/ppa && \
    apt-get update && \
    apt-get install -y python3.11 python3.11-distutils python3.11-dev python3.11-venv && \
    rm -rf /var/lib/apt/lists/*

# Installa pip per Python 3.11
RUN wget https://bootstrap.pypa.io/get-pip.py && \
    python3.11 get-pip.py && \
    rm get-pip.py

# --- Installazione di Blender 5.0 ---
WORKDIR /opt
# Scarica ed estrai Blender 5.0
RUN wget https://download.blender.org/release/Blender5.0/blender-5.0.0-linux-x64.tar.xz && \
    tar -xf blender-5.0.0-linux-x64.tar.xz && \
    rm blender-5.0.0-linux-x64.tar.xz && \
    mv blender-5.0.0-linux-x64 blender

# Aggiungi Blender al PATH
ENV PATH="/opt/blender:$PATH"

# Installa gmsh nell'ambiente Python di Blender
RUN /opt/blender/*/python/bin/python3* -m ensurepip && \
    /opt/blender/*/python/bin/python3* -m pip install gmsh opencv-python

# --- Installazione di PartUV ---
WORKDIR /workspace

# Crea un virtual environment per PartUV per isolare le dipendenze
RUN python3.11 -m venv /opt/partuv_env
ENV PATH="/opt/partuv_env/bin:$PATH"

# Installa PyTorch 2.7.1 con supporto CUDA 12.8 e torch-scatter
# Nota: Gli URL dei wheel sono presi dalla documentazione di PartUV
RUN pip install --upgrade pip && \
    pip install torch==2.7.1 --index-url https://download.pytorch.org/whl/cu128 && \
    pip install torch-scatter -f https://data.pyg.org/whl/torch-2.7.1+cu128.html

# Clona il repository PartUV
RUN git clone https://github.com/EricWang12/PartUV.git

WORKDIR /workspace/PartUV

# Installa i requisiti e il pacchetto PartUV
# Modifica requirements.txt per imporre versioni specifiche
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

# Comando di default
CMD ["/bin/bash"]
