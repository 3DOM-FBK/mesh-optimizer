import bpy
import os
import sys
import argparse
import bmesh
import shutil


# ===== Function: parse_arguments =====
def parse_arguments():
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = []

    parser = argparse.ArgumentParser(description="Process 3D model baking parameters.")
    parser.add_argument('-i', '--input_file', type=str, required=True, help='Input file')
    parser.add_argument('-o', '--output_folder', type=str, required=True, help='Output folder')
    parser.add_argument('-f', '--output_format', type=str, required=True, help='Output format')
    parser.add_argument('-n', '--model_name', type=str, required=True, help='Model name')

    return parser.parse_args(argv)


# ===== Function: import_model =====
def import_model(filepath):
    """
    Import a 3D model into Blender based on its file extension.

    Supported formats:
        - .obj : Wavefront OBJ
        - .fbx : Autodesk FBX
        - .ply : Polygon File Format
        - .stl : STL mesh

    Args:
        filepath (str): The full path to the 3D model file to import.

    Returns:
        bpy.types.Object: The first object selected after import.

    Raises:
        ValueError: If the file extension is not supported.
    """
    ext = os.path.splitext(filepath)[1].lower()
    if ext == ".obj":
        bpy.ops.wm.obj_import(filepath=filepath)
    elif ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=filepath)
    elif ext == ".ply":
        bpy.ops.import_mesh.ply(filepath=filepath)
    elif ext == ".stl":
        bpy.ops.import_mesh.stl(filepath=filepath)
    elif ext in [".glb", ".gltf"]:
        bpy.ops.import_scene.gltf(filepath=filepath, merge_vertices=True)
    else:
        raise ValueError(f"Unsupported format: {ext}")
    return bpy.context.selected_objects[0]


# ===== Function: export_model =====
def export_model(obj, filepath):
    """
    Export a single Blender mesh object to a specified file format.

    Supported formats:
        - .obj  : Wavefront OBJ
        - .fbx  : Autodesk FBX
        - .gltf : GLTF/GLB embedded
        - .glb  : GLB binary
        - .ply  : Polygon File Format
        - .usd  : Universal Scene Description

    The function deselects all objects, selects only the provided mesh object,
    and exports it to the given filepath in the format determined by the file extension.

    Args:
        obj (bpy.types.Object): The Blender mesh object to export.
        filepath (str): The full path where the exported file will be saved.

    Raises:
        TypeError: If the provided object is not a mesh.
        ValueError: If the file extension is not supported.
    """
    ext = os.path.splitext(filepath)[1].lower()
    if obj.type != 'MESH':
        raise TypeError(f"Object '{obj.name}' is not a mesh.")
    
    # Deselect everything
    bpy.ops.object.select_all(action='DESELECT')

    # Select only the object we want to export
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    
    if ext == ".obj":
        bpy.ops.wm.obj_export(filepath=filepath, export_selected_objects=True, export_materials=False)
    elif ext == ".fbx":
        bpy.ops.export_scene.fbx(filepath=filepath, use_selection=True)
    elif ext == ".gltf":
        bpy.ops.export_scene.gltf(filepath=filepath, use_selection=True, export_format='GLTF_SEPARATE')
    elif ext == ".glb":
        bpy.ops.export_scene.gltf(filepath=filepath, use_selection=True, export_format='GLB')
    elif ext == ".ply":
        bpy.ops.export_mesh.ply(filepath=filepath, use_selection=True)
    elif ext == ".usd":
        bpy.ops.wm.usd_export(filepath=filepath, selected_objects_only=True)
    else:
        raise ValueError(f"Unsupported format: {ext}")
    

# ===== Function: move_png_files =====
def move_png_files(src_dir: str, dst_dir: str):
    """
    Move all PNG files from a source directory to a destination directory.

    Args:
        src_dir (str): Path to the source directory containing PNG files.
        dst_dir (str): Path to the destination directory where files will be moved.

    Notes:
        - Only files with the '.png' extension (case-insensitive) are moved.
        - Existing files in the destination with the same name may be overwritten.
    """
    for file_name in os.listdir(src_dir):
        if file_name.lower().endswith(".png"):
            src_path = os.path.join(src_dir, file_name)
            dst_path = os.path.join(dst_dir, file_name)
            shutil.move(src_path, dst_path)


# ===== Function: clean_tmp =====
def clean_tmp(tmp_dir="/tmp"):
    """
    Remove all files and subdirectories from a specified temporary directory.

    Args:
        tmp_dir (str, optional): Path to the directory to clean. Defaults to "/tmp".

    Notes:
        - The directory itself is not removed, only its contents.
        - Files, symbolic links, and subdirectories are deleted.
        - Errors during deletion are caught and printed, but do not stop the process.
    """
    if not os.path.exists(tmp_dir):
        return

    for entry in os.listdir(tmp_dir):
        path = os.path.join(tmp_dir, entry)
        try:
            if os.path.isfile(path) or os.path.islink(path):
                os.remove(path)
            elif os.path.isdir(path):
                shutil.rmtree(path)
        except Exception as e:
            print(f"Errore durante la rimozione di {path}: {e}")
    

if __name__ == "__main__":
    args = parse_arguments()

    model = import_model(args.input_file)

    new_folder = os.path.join(args.output_folder, args.model_name)
    os.makedirs(new_folder, exist_ok=True)

    new_folder_tex = os.path.join(args.output_folder, args.model_name, "tex")
    os.makedirs(new_folder_tex, exist_ok=True)

    base, _ = os.path.splitext(args.input_file)
    new_name = f"{args.model_name}_optimize.{args.output_format}"

    output_path = os .path.join(new_folder, new_name)
    
    export_model(model, output_path)

    move_png_files("/tmp", new_folder_tex)

    clean_tmp()
