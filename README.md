# mesh-optimizer - 3D Mesh Optimization Pipeline
The project is a pipeline for 3D mesh optimization, designed to process 3D models (e.g., in OBJ format) through a series of automated steps that include cleaning, remeshing, decimation, material enhancement, and format conversion. It is intended to run in a Docker environment, leveraging both C++ tools (for remeshing) and Python scripts (for manipulation via Blender and other libraries).

---

## General Features

- **Automated 3D Mesh Optimization**: The pipeline takes one or more 3D models as input and processes them according to a configurable sequence of steps.  
- **Advanced Remeshing**: Uses a high-performance C++ executable for adaptive mesh remeshing.  
- **Decimation**: Reduces the number of polygons while preserving the overall shape of the model.  
- **Geometric Cleaning**: Removes unnecessary or problematic geometries.  
- **Material Enhancement**: Generates Ambient Occlusion and Roughness maps and manages textures.  
- **Format Conversion**: Exports optimized models in various formats (OBJ, GLTF, FBX, USD, etc.).  
- **Automation and Reproducibility**: Orchestrated via a main script (`main.py`) and configurable through YAML.

---

## Main Modules

### 1. `main.py`
- Entry point of the pipeline.  
- Loads the configuration (`config.yaml`).  
- Handles logging.  
- Orchestration: sequentially calls Python scripts and the C++ executable for each model.  
- Main functions: cleaning, remeshing, decimation, material enhancement, format conversion.  
- Utilizes functions such as `PipelineProcessor.run_cleanup`, `PipelineProcessor.run_remesh`, `PipelineProcessor.run_decimate`, `PipelineProcessor.improve_material`, `PipelineProcessor.format_conversion`.

### 2. `cleanup_geo.py`
Python script using Blender to:  
- Clean the scene.  
- Import the model.  
- Remove isolated geometries.  
- Triangulate the mesh.  
- Export the cleaned model.

### 3. `remesh.py`
Python script that:  
- Can run the C++ executable for remeshing via `run_cpp_executable`.  
- Also handles UV mapping and texture baking via Python libraries (trimesh, xatlas, etc.).

### 4. `decimate.py`
Python script using Blender to apply a decimation modifier to the mesh, reducing the number of polygons according to a configurable ratio.

### 5. `improve_material.py`
Python script that:  
- Generates roughness and ambient occlusion maps.  
- Handles model import and texture baking via Blender and OpenCV.

### 6. `file_conversion.py`
Python script that imports the optimized model and exports it in the desired format, also managing textures.

### 7. `c++/source/build/remesh`
C++ executable (compiled from `c++/source/remesh.cpp`) implementing a high-performance adaptive remeshing algorithm, using libraries such as PMP, CGAL, Eigen, and TBB.

### 8. `config.yaml`
Configuration file defining the pipeline (which steps to run, output parameters, list of models to process, etc.).

---

## Summary

The project automates 3D mesh optimization through a modular pipeline, combining C++ and Python/Blender tools, with centralized configuration and support for multiple output formats.  
Detailed information for each module can be found in their respective files, e.g., `main.py`, `remesh.py`, `cleanup_geo.py`, `decimate.py`, `improve_material.py`, `file_conversion.py`, `remesh.cpp`, and `config.yaml`.