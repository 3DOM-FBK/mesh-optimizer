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
- Aggregating results and generating a final report (statistics on triangles, timings, quality).

---

## Features in the pipelines Folder

The pipelines folder contains the scripts/modules implementing each step of the pipeline.
Below are the main functionalities per module (note: the deprecated and c++ folders are excluded):

- cleanup_geo.py
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

- improve_material.py
  - Bakes maps such as Ambient Occlusion, Normal map, Roughness, Emission if required.
  - Cleans and normalizes textures, converts channels, and optimizes images (resolution reduction, compression).
  - Optionally generates standardized PBR materials.

- file_conversion.py
  - Imports the optimized result and exports it into the requested format (GLTF/GLB).
  - Manages texture paths and relative/absolute references.
  - Options to embed textures or save them as separate files.

---

## How the Pipeline Is Organized (Typical Workflow)

1. main.py loads configuration and creates the working directory.
2. cleanup_geo → produces the cleaned mesh.
3. remesh → (optional) advanced remeshing.
4. decimate → reduces polygons according to the target.
5. improve_material → texture baking and optimization.
6. file_conversion → export to the final format.
7. Final report with quality metrics and output sizes.

---

## Where to Look for Further Details

- main.py — pipeline orchestration and configuration.
- pipelines/cleanup_geo.py, pipelines/remesh.py, pipelines/decimate.py, pipelines/improve_material.py, pipelines/file_conversion.py — implementation of each step.
- config/config.yaml — parameters and execution sequence.