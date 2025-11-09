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
    parser.add_argument('-o', '--output_file', type=str, required=True, help='Output file')
    
    # Replace target_count with quality parameter
    parser.add_argument(
        '-q', '--quality',
        type=str,
        choices=['high', 'medium', 'low'],  # only these 3 are allowed
        default='low',                   # optional default
        help='Target quality: high, medium, or low'
    )

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
        - .glb/gltf

    Args:
        filepath (str): The full path to the 3D model file to import.

    Returns:
        bpy.types.Object: The first object selected after import.

    Raises:
        ValueError: If the file extension is not supported.
    """
    ext = os.path.splitext(filepath)[1].lower()
    if ext in [".glb", ".gltf"]:
        bpy.ops.import_scene.gltf(
            filepath=filepath,
            merge_vertices=True
        )
    else:
        raise ValueError(f"Unsupported format: {ext}")
    return bpy.context.selected_objects[0]


# ===== Function: export_model =====
def export_model(obj, filepath):
    """
    Export a single Blender mesh object to a specified file format.

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


# ===== Function: merge_vertices =====
def merge_vertices(obj, distance=0.0001):
    """
    Merge nearby vertices of a Blender mesh object within a specified distance.

    This function selects all vertices of the given mesh and merges
    those that are closer than the specified threshold, effectively cleaning up duplicate or overlapping vertices.

    Args:
        obj (bpy.types.Object): The Blender mesh object to process.
        distance (float, optional): Maximum distance between vertices to merge (default: 0.0001).

    Notes:
        - The function switches to Edit Mode to perform the operation and returns to Object Mode afterward.
    """
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj

    bpy.ops.object.mode_set(mode='EDIT')

    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.remove_doubles(threshold=distance)

    bpy.ops.object.mode_set(mode='OBJECT')


    """
    Compute a decimation ratio (0-1) based on the mesh and desired quality.
    
    Args:
        model: Blender object (mesh)
        quality: 'high', 'medium', or 'low'
    
    Returns:
        float: decimation ratio to use in Blender (1.0 = no decimation)
    """
    current_polys = get_polygon_count(model)
    
    # Define target poly counts for medium/low quality
    target_counts = {
        'high': current_polys,     # no decimation
        'medium': 50000,           # medium poly count target
        'low': 10000               # low poly count target
    }
    
    if quality not in target_counts:
        raise ValueError("Quality must be 'high', 'medium', or 'low'")
    
    target = target_counts[quality]
    
    # If current is lower than target, no decimation needed
    if current_polys <= target or quality == 'high':
        return 1.0
    
    # Decimation ratio = target / current
    ratio = target / current_polys
    return max(min(ratio, 1.0), 0.0)  # clamp between 0 and 1


# ===== Function: get_polygon_count =====
def get_polygon_count(obj):
    """Return the number of polygons of a Blender mesh object."""
    if obj.type != 'MESH':
        raise TypeError(f"Object '{obj.name}' is not a mesh")
    return len(obj.data.polygons)


# ===== Function: get_mesh_volume =====
def get_mesh_volume(obj):
    """Estimate the mesh volume using the bounding box."""
    bbox = obj.bound_box  # 8 vertices in local space
    # Compute dimensions
    dims = [max(v[i] for v in bbox) - min(v[i] for v in bbox) for i in range(3)]
    volume_estimate = dims[0] * dims[1] * dims[2]
    return volume_estimate


# ===== Function: get_decimation_ratio =====
def get_decimation_ratio(model, quality):
    """
    Compute a decimation ratio (0-1) based on mesh size and desired quality.

    Args:
        model: Blender object (mesh)
        quality: 'high', 'medium', or 'low'

    Returns:
        float: decimation ratio to use in Blender (1.0 = no decimation)
    """
    current_polys = get_polygon_count(model)
    volume = get_mesh_volume(model)

    # Define polygon density per unit volume for each quality level
    polygon_density = {
        'high': 5000,    # polys per unit^3
        'medium': 3000,
        'low': 200
    }

    if quality not in polygon_density:
        raise ValueError("Quality must be 'high', 'medium', or 'low'")

    # Calculate target polygon count based on volume
    target_polys = int(volume * polygon_density[quality])

    # If current polys are lower than target or high quality, no decimation
    if current_polys <= target_polys or quality == 'high':
        return 1.0

    # Decimation ratio
    ratio = target_polys / current_polys
    return max(min(ratio, 1.0), 0.0)  # clamp between 0 and 1


if __name__ == "__main__":
    args = parse_arguments()

    model = import_model(args.input_file)

    merge_vertices(model)

    decimate_ratio = get_decimation_ratio(model, args.quality)

    apply_decimate_modifier(model, decimate_ratio)

    export_model(model, args.output_file)