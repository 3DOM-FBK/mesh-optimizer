# mesh-optimizer – 3D Mesh Optimization Pipeline

Modular pipeline for automated optimization of 3D meshes (input: OBJ, GLB, GLTF).
The project orchestrates a sequence of steps — cleaning, remeshing, decimation, material improvement, and format conversion — through a main script and Python modules executed (typically) inside Blender or with standard Python, C++ libraries.
The project is designed for reproducible execution (e.g., in Docker).

---

## General Features

- Automatic and repeatable execution of an optimization sequence for one or multiple models.
- Support for various input/output formats (OBJ, GLTF/GLB, FBX).
- Integration of high-performance tools for remeshing and geometric transformations.
- Generation and management of material maps (AO, Roughness, etc.).
- Centralized configuration through YAML and detailed logging.

---

## Starting from main.py

main.py is the entry point and orchestrator of the pipeline. Its main responsibilities include:
- Loading configuration settings (e.g., config/config.yaml) and validating parameters.
- Setting up logging and the working/output folder structure.
- For each input model, executing the configured sequence of steps (cleaning → remesh → decimate → material → export).
- Calling Python modules located in the pipelines folder and, if configured, external executables (native remesher).
- Handling errors and applying retry/skip policies for failed steps.

---

## Features in the pipelines Folder

The pipelines folder contains the scripts/modules implementing each step of the pipeline.
Below are the main functionalities per module (note: the deprecated and c++ folders are excluded):

- preprocess_model.py
  - Imports the model into Blender or via Python libraries.
  - Removes disconnected/isolated geometry, duplicate vertices, and degenerate faces.
  - Applies transformations (scale/rotation), basic unwrapping, and triangulation.
  - Exports the “cleaned” mesh for the following steps.

- remesh.py
  - Interfaces with the external remeshing executable — MMG Library.
  - Adaptive parameters for controlling face density, edge preservation, and triangulation quality.
  - Produces meshes with regular topology suitable for decimation and texture baking.

- decimate.py
  - Applies decimation algorithms (Blender modifier).
  - Supports percentage thresholds or a target triangle count.
  - Preserves UVs and minimizes visual artifacts.

- texture_generator.py
  - Bakes maps such as Ambient Occlusion, Normal map, Roughness, Emission if required.
  - Cleans and normalizes textures, converts channels, and optimizes images (resolution reduction, compression).
  - Generates standardized PBR materials.
  - Manages texture paths and relative/absolute references.
  - Options to embed textures or save them as separate files.

---

## How the Pipeline Is Organized (Typical Workflow)

1. main.py loads configuration and creates the working directory.
2. preprocess_model → produces the cleaned mesh.
3. remesh → (optional) advanced remeshing.
4. decimate → reduces polygons according to the target.
5. texture_generator → texture baking, optimization and export to the final format.
6. file_conversion → export to the final format.

---

## Where to Look for Further Details

- main.py — pipeline orchestration and configuration.
- pipelines/preprocess_model.py, pipelines/remesh.py, pipelines/decimate.py, pipelines/texture_generator.py — implementation of each step.
- config/config.yaml — parameters and execution sequence.

## Running with Docker
The pipeline is available as a Docker image on Docker Hub, which allows you to run the code in a reproducible environment with all dependencies pre-installed.

- **Docker image**: 3domfbk/mesh-optimizer:21112025

#### Basic usage
To run the container with GPU support and mount your data folder:
```
docker run --rm -it --gpus all -v <local_data_path>:<container_data_path> 3domfbk/mesh-optimizer:21112025 -h
```

## Config example:
```
# Pipeline Global Config - Optimization model
pipeline:
  image_size: 2048                          # resolution of output images
  output_dir: "/data/output/New_Test"       # output folder for processed files
  quality: "medium"                         # define decimation quality preset: high, medium and low
  remesh: false                             # enable/disable remeshing step
  verbose: 0

models:
  - path: "/data/input/glb/building.glb"
  # - path: "/data/input/glb/casa.glb"
  # - path: "/data/input/glb/Surdulica.glb"
  ```