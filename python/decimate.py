import bpy
import os
import sys
import argparse
import bmesh


# ===== Function: parse_arguments =====
def parse_arguments():
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = []

    parser = argparse.ArgumentParser(description="Process 3D model baking parameters.")
    parser.add_argument('-i', '--input_file', type=str, required=True, help='Input file')
    parser.add_argument('-d', '--decimate_ratio', type=str, help='decimate_ratio')

    return parser.parse_args(argv)


# ===== Function: apply_decimate_modifier =====
def apply_decimate_modifier(model, decimate_ratio=0.5):
    """
    Apply a Decimate modifier to a Blender mesh object to reduce its polygon count.

    This function adds a Decimate modifier with the specified ratio and applies it,
    optionally collapsing and triangulating faces to maintain mesh integrity.

    Args:
        model (bpy.types.Object): The Blender mesh object to decimate.
        decimate_ratio (float, optional): The target ratio of remaining geometry (0 < ratio <= 1.0).

    Raises:
        TypeError: If the provided object is not a mesh.
        ValueError: If decimate_ratio is not between 0 (exclusive) and 1 (inclusive).
    """
    if model.type != 'MESH':
        raise TypeError(f"modelect '{model.name}' is not a mesh.")
    if not (0.0 < float(decimate_ratio) <= 1.0):
        raise ValueError("decimate_ratio must be between 0 (exclusive) and 1 (inclusive).")

    # Add Decimate modifier
    mod = model.modifiers.new(name="Decimate", type='DECIMATE')
    mod.ratio = float(decimate_ratio)
    mod.use_collapse_triangulate = True  # Optional: helps keep triangles

    # Apply modifier
    bpy.context.view_layer.objects.active = model
    bpy.ops.object.modifier_apply(modifier=mod.name)


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
    if ext in [".glb", ".gltf"]:
        bpy.ops.import_scene.gltf(filepath=filepath, merge_vertices=True)
    else:
        raise ValueError(f"Unsupported format: {ext}")
    return bpy.context.selected_objects[0]


# ===== Function: export_model =====
def export_model(obj, filepath):
    """
    Export a single Blender mesh object to a specified file format.

    Currently, only the OBJ format is supported.

    The function deselects all objects, selects only the provided mesh object,
    and exports it to the given filepath.

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
    
    if ext == ".glb":
        bpy.ops.export_scene.gltf(
            filepath=filepath,
            use_selection=True
        )
    else:
        raise ValueError(f"Unsupported format: {ext}")


if __name__ == "__main__":
    args = parse_arguments()
    filepath = "/tmp/model.glb"

    model = import_model(args.input_file)

    apply_decimate_modifier(model, decimate_ratio=args.decimate_ratio)

    export_model(model, filepath)