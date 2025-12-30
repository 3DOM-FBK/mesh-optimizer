# Mesh Optimizer

**A comprehensive, automated pipeline for 3D mesh optimization, designed for high-throughput processing of 3D assets.**

This repository hosts a robust Python-based orchestration pipeline that leverages **Blender**, **CGAL**, and machine learning techniques to optimize 3D models. It covers the entire lifecycle of mesh optimization: from geometry cleaning and isotropic remeshing to UV unwrapping, texture baking, and final decimation.

Developed by the **3DOM** unit at **FBK** (Fondazione Bruno Kessler).

---

## 🚀 Key Features

*   **Automated Workflow**: Seamlessly orchestrates multiple complex processing steps (Cleanup $\rightarrow$ Remeshing $\rightarrow$ Decimation $\rightarrow$ UV $\rightarrow$ Baking).
*   **High-Quality Remeshing**: Integrates **CGAL** for heavy-duty adaptive isotropic remeshing, creating clean and regular topology suitable for simulation and baking.
*   **Intelligent Decimation**: Preserves visual fidelity while reducing polygon counts using configurable presets (`LOW`, `MEDIUM`, `HIGH`).
*   **Advanced UV Unwrapping**: Utilizes **PartUV** (Machine Learning) for semantic part segmentation and optimized UV island packing, ensuring efficient texture space usage.
*   **PBR Texture Baking**: Automatically bakes high-resolution geometric details (Normal, Ambient Occlusion, Roughness) onto the optimized low-poly mesh.
*   **Format Support**: Robust handling of standard formats like **OBJ**, **GLB**, and **GLTF**.
*   **Containerized**: Fully Dockerized for reproducible, dependency-free execution on any infrastructure (with GPU support).

---

## 🛠️ Pipeline Architecture

The pipeline follows a rigorous sequence of operations to ensure quality:

1.  **Import & Cleanup**: Input models are imported and sanitized. This includes removing isolated vertices, degenerate faces, and duplicate geometry.
2.  **Preprocessing**: Geometry is scaled and prepared for the optimization loop.
3.  **Adaptive Remeshing**: The high-poly mesh is remeshed using CGAL to ensure uniform edge lengths and regular topology.
4.  **Initial Decimation**: Geometry is reduced to a manageable intermediate target (e.g., 300k faces) to facilitate efficient UV generation.
5.  **UV Generation**: **PartUV** is invoked to segment the mesh and generate UV maps based on semantic understanding of the shape.
6.  **Texture Baking**: Comparison between the original High-Poly mesh and the new Low-Poly mesh generates detailed PBR maps (Normal, AO, Roughness).
7.  **Final Decimation**: The mesh is further optimized based on the selected quality target/preset.
8.  **Export**: The final asset is packaged and exported as a GLB file with embedded textures.

---

## 📦 Installation & Usage

The recommended way to run Mesh Optimizer is via **Docker** to handle the complex C++ and Python dependencies (Blender, CGAL, PyTorch).

### 🐳 Docker Usage

To run the pipeline using the official image:

```bash
docker run --rm -it --gpus all \
  -v /path/to/local/data:/data \
  3domfbk/mesh-optimizer:30122025 \
  --config /data/config.yaml
```

**Parameters:**
*   `--gpus all`: Required for CUDA-accelerated texture baking and PartUV inference.
*   `-v`: Mounts your local data directory into the container.

### 🐍 Local Python Usage

If running locally (requires Blender 3.x/4.x in PATH and configured Python environment):

```bash
python main.py --config config/config.yaml
```

---

## ⚙️ Configuration

The pipeline is controlled via a simple YAML configuration file.

**Example `config.yaml`:**

```yaml
# Pipeline Global Config
pipeline:
  image_resolution: 2048                # Output Texture size: 1024, 2048, 4096
  output_dir: "/data/output/optimized"  # Destination for processed files
  quality: "MEDIUM"                     # Optimization target: LOW, MEDIUM, HIGH

models:
  - path: "/data/input/scanned_statue.obj"
  - path: "/data/input/building_scan.glb"
  # - path: "/data/input/another_mesh.obj"
```

| Parameter | Options | Description |
| :--- | :--- | :--- |
| `image_resolution` | `1024`, `2048`, `4096` | Resolution of the baked texture maps. |
| `quality` | `LOW`, `MEDIUM`, `HIGH` | Controls the target face count for the final decimation. |

---

## 📚 Citations & Acknowledgments

This project integrates several open-source technologies and research works. If you use this pipeline in your research or work, please acknowledge the following:

*   **Blender**: The core 3D processing engine. [https://www.blender.org/](https://www.blender.org/)
*   **CGAL**: The Computational Geometry Algorithms Library, used for high-fidelity remeshing. [https://www.cgal.org/](https://www.cgal.org/)
*   **PartUV**: Utilized for semantic UV segmentation and packing.
    *   *Reference*: [PartUV Repository / Paper](https://github.com/EricWang12/PartUV)
*   **Objaverse**: Provide data foundations for trained checkpoints used in segmentation.

---

*© 3DOM - FBK. All rights reserved.*