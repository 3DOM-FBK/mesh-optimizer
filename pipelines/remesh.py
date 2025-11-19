import os
import sys
import subprocess
import gmsh
import bpy
import argparse


# ===== Function: parse_arguments =====
def parse_arguments():
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = []

    parser = argparse.ArgumentParser(description="Process 3D model parameters.")
    parser.add_argument('-i', '--dir_path', type=str, required=True, help='Input dir path')

    return parser.parse_args(argv)


# ===== Function: run_cpp_executable =====
def run_cpp_executable(args=None, verbose=0):
    """
    Run a C++ executable with optional command-line arguments and capture its output.

    Args:
        executable_path (str): Full path to the C++ executable to run.
        args (list, optional): List of arguments to pass to the executable (default: empty list).
        verbose (bool, optional): If True, prints the stdout and stderr of the process (default: False).

    Returns:
        bool: True if the executable ran successfully (exit code 0), False otherwise.

    Notes:
        - Uses subprocess.run with capture_output and text mode.
        - Exceptions and non-zero exit codes are caught and return False.
    """
    cmd = [os.path.abspath('/opt/mmg/build/bin/mmgs_O3')]

    if args is None:
        args = []

    if args:
        cmd.extend(args)

    try:
        if (verbose == 1):
            res = subprocess.run(cmd)
        else:
            res = subprocess.run(cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL
            )
        return True
    except:
        return False

# ===== Function: import_model =====
def import_model(filepath):
    """
    Import a 3D model (.glb/.gltf) into Blender.
    
    Args:
        filepath (str): The full path to the model file.
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"File not found: {filepath}")
    
    ext = os.path.splitext(filepath)[1].lower()

    bpy.ops.object.select_all(action='DESELECT')

    if ext == ".obj":
        bpy.ops.wm.obj_import(filepath=filepath)
    elif ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(
            filepath=filepath,
            merge_vertices=True
        )
    else:
        raise ValueError(f"Unsupported file format: {ext}")

    return bpy.context.selected_objects[0]


# ===== Function: export_model =====
def export_model(model, dir_path, ext=".glb", use_selection=True):
    """
    Export the current Blender scene or selected objects to a .glb file.
    
    Args:
        filepath (str): The full path where the .glb file will be saved.
        use_selection (bool): If True, export only selected objects.
    """
    if model.type != 'MESH':
        raise TypeError(f"Object '{model.name}' is not a mesh.")
    
    # Deselect everything
    bpy.ops.object.select_all(action='DESELECT')

    # Select only the object we want to export
    model.select_set(True)
    bpy.context.view_layer.objects.active = model

    filepath = os.path.join(dir_path, f"remesh{ext}")

    if (ext == ".glb"):
        bpy.ops.export_scene.gltf(
            filepath=filepath,
            export_format='GLB',
            use_selection=use_selection
        )
    elif (ext == ".obj"):
        bpy.ops.wm.obj_export(
            filepath=filepath,
            export_materials=False
        )


# ===== Function: preprocess_mmg =====
def preprocess_mmg(file_path):
    """
    Pre-processes a 3D model file for remeshing with MMG via Gmsh.
    
    This function:
    1. Initializes Gmsh.
    2. Imports the given 3D model file (STL, STEP, etc.).
    3. Generates a 3D mesh.
    4. Writes the resulting mesh to a `.mesh` file in the same folder as the input file,
       using the same base name.
    5. Finalizes Gmsh.

    Parameters:
    file_path (str): Path to the input 3D model file.
    """
    # Initialize Gmsh
    gmsh.initialize()

    # Import the model
    gmsh.merge(file_path)

    # Generate a 3D mesh
    gmsh.model.mesh.generate(3)

    # Extract folder and base name from the input file
    folder = os.path.dirname(file_path)
    base_name = os.path.splitext(os.path.basename(file_path))[0]

    # Construct output path for the .mesh file
    out_path = os.path.join(folder, f"{base_name}.mesh")
    mmg_out_path = os.path.join(folder, f"{base_name}_res.mesh")

    # Write the mesh
    gmsh.write(out_path)

    # Finalize Gmsh
    gmsh.finalize()

    return out_path, mmg_out_path


# ===== Function: postprocess_mmg =====
def postprocess_mmg(file_path):
    """
    Converts a `.mesh` file produced for MMG back into a Wavefront OBJ file.

    This function:
    1. Initializes Gmsh.
    2. Imports the `.mesh` file.
    3. Exports the geometry/triangular mesh as a `.obj` file in the same folder,
       using the same base name.
    4. Finalizes Gmsh.
    
    Parameters:
    file_path (str): Path to the input .mesh file.

    Returns:
    str: Path to the generated .obj file.
    """
    # Initialize Gmsh
    gmsh.initialize()

    # Load the .mesh file
    gmsh.merge(file_path)

    # Extract folder and base name
    folder = os.path.dirname(file_path)
    base_name = os.path.splitext(os.path.basename(file_path))[0]

    # Construct OBJ output path
    obj_path = os.path.join(folder, f"{base_name}.obj")

    # Write the OBJ file
    gmsh.write(obj_path)

    # Finalize Gmsh
    gmsh.finalize()

    return obj_path


# ===== Function: remesh_geometry =====
def remesh_geometry(file_path):
    mmg_infile, mmg_out_path = preprocess_mmg(file_path)
    
    args = ["-in", mmg_infile, "-out", mmg_out_path]
    res = run_cpp_executable(args)

    obj_path = postprocess_mmg(mmg_out_path)

    return res, obj_path


# ===== Function: remove_temp_data =====
def remove_temp_data(dir_path):
    """
    Deletes all temporary mesh files inside the given directory and its subdirectories.

    This function removes:
    - all .obj files
    - all .mesh files

    Parameters:
    dir_path (str): Root directory where temporary files will be deleted.
    """
    # File patterns to delete
    patterns = ["*.obj", "*.mesh"]

    for pattern in patterns:
        files = glob.glob(os.path.join(dir_path, "**", pattern), recursive=True)

        for file_path in files:
            try:
                os.remove(file_path)
            except Exception:
                pass


if __name__ == "__main__":
    """
    Main pipeline:
    - Export OBJ mesh
    - Perform remeshing
    - Import remeshed mesh
    - Export final mesh as GLB
    - Clean temporary data
    """
    args = parse_arguments()
    dir_path = args.dir_path

    temp_remesh = os.path.join(dir_path, "remesh.obj")
    temp_glb = os.path.join(dir_path, "temp_model.glb")

    # Start clean
    bpy.ops.wm.read_factory_settings(use_empty=True)

    # Import model
    model = import_model(temp_glb)

    # Export as .obj for remeshing
    export_model(model, dir_path, ext=".obj", use_selection=True)

    # Perform remeshing
    res_remesh, obj_path = remesh_geometry(temp_remesh)
    if res_remesh:
        # Reset scene to avoid duplicate data
        bpy.ops.wm.read_factory_settings(use_empty=True)

        # Import remeshed model
        print ("--> Importing remeshed model:", obj_path)
        model = import_model(obj_path)

        # Export final .glb
        export_model(model, dir_path, ext=".glb", use_selection=True)
    else:
        sys.exit(1)

    # Cleanup
    remove_temp_data(dir_path)