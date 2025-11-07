import bpy
import os
import bmesh
import sys
import argparse
import subprocess
import glob


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
def run_cpp_executable(executable_path, args=None, verbose=False):
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
    if args is None:
        args = []

    try:
        result = subprocess.run(
            [executable_path] + args,
            capture_output=True,
            text=True,
            check=True  # Raises CalledProcessError if returncode != 0
        )
        if verbose:
            print("[STDOUT]\n", result.stdout)
            print("[STDERR]\n", result.stderr)
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
        bpy.ops.import_scene.gltf(filepath=filepath)
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

    filepath = os.path.join(dir_path, f"temp_model_remesh{ext}")

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


# ===== Function: remesh_geometry =====
def remesh_geometry(file_path):
    remesh_exec = os.path.abspath('/opt/adaptive_remesh')
    res = run_cpp_executable(remesh_exec, [file_path, file_path])

    return res


# ===== Function: generate_uv_smart_project =====
def generate_uv_smart_project(low_model,
                              angle_limit=66.0,
                              island_margin=0.0,
                              area_weight=0.0,
                              correct_aspect=True,
                              scale_to_bounds=True):
    """
    Generate UV
    """
    bpy.ops.object.select_all(action='DESELECT')
    low_model.select_set(True)
    bpy.context.view_layer.objects.active = low_model

    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')

    bpy.ops.uv.smart_project(
        angle_limit=angle_limit,
        island_margin=island_margin,
        area_weight=area_weight,
        correct_aspect=correct_aspect,
        scale_to_bounds=scale_to_bounds
    )

    bpy.ops.object.mode_set(mode='OBJECT')


# ===== Function: remove_temp_data =====
def remove_temp_data(dir_path):
    """
    Delete all .obj files inside /tmp and its subdirectories.
    """
    obj_files = glob.glob(os.path.join(dir_path, "**", "*.obj"), recursive=True)

    for file_path in obj_files:
        try:
            os.remove(file_path)
        except Exception as e:
            pass

if __name__ == "__main__":
    """
    Main pipeline:
    - Export OBJ mesh
    - Perform remeshing
    - Import remeshed mesh
    - Generate UV maps (Smart Project)
    - Export final mesh as GLB
    - Clean temporary data
    """
    args = parse_arguments()
    dir_path = args.dir_path

    temp_remesh = os.path.join(dir_path, "temp_model_remesh.obj")
    temp_glb = os.path.join(dir_path, "temp_model.glb")

    # Start clean
    bpy.ops.wm.read_factory_settings(use_empty=True)

    # Import model
    model = import_model(temp_glb)

    # Export as .obj for remeshing
    export_model(model, dir_path, ext=".obj", use_selection=True)

    # Perform remeshing
    if remesh_geometry(temp_remesh):
        # Reset scene to avoid duplicate data
        bpy.ops.wm.read_factory_settings(use_empty=True)

        # Import remeshed model
        model = import_model(temp_remesh)

        # Generate UVs
        generate_uv_smart_project(model)

        # Export final .glb
        export_model(model, dir_path, ext=".glb", use_selection=True)

    # Cleanup
    remove_temp_data(dir_path)