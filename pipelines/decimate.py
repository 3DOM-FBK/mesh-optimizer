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
        default='medium',                   # optional default
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


# ===== Function: compute_hausdorff_distance =====
def compute_hausdorff_distance(obj_a, obj_b, samples=5000):
    """
    Approximate Hausdorff distance between two meshes by random sampling.
    Uses closest_point_on_mesh to compute distances.
    """
    import random
    depsgraph = bpy.context.evaluated_depsgraph_get()

    mesh_a = obj_a.evaluated_get(depsgraph).to_mesh()
    mesh_b = obj_b.evaluated_get(depsgraph).to_mesh()

    bm_a = bmesh.new()
    bm_a.from_mesh(mesh_a)
    bm_a.verts.ensure_lookup_table()

    bm_b = bmesh.new()
    bm_b.from_mesh(mesh_b)
    bm_b.verts.ensure_lookup_table()

    total_verts_a = len(bm_a.verts)
    total_verts_b = len(bm_b.verts)

    # Sample random vertices (approximate)
    verts_a = random.sample(list(bm_a.verts), min(samples, total_verts_a))
    verts_b = random.sample(list(bm_b.verts), min(samples, total_verts_b))

    max_dist = 0.0

    # Distance from A to B
    for v in verts_a:
        _, loc, _, _ = obj_b.closest_point_on_mesh(v.co)
        dist = (v.co - loc).length
        if dist > max_dist:
            max_dist = dist

    # Distance from B to A
    for v in verts_b:
        _, loc, _, _ = obj_a.closest_point_on_mesh(v.co)
        dist = (v.co - loc).length
        if dist > max_dist:
            max_dist = dist

    # Cleanup
    bm_a.free()
    bm_b.free()
    obj_a.to_mesh_clear()
    obj_b.to_mesh_clear()

    return max_dist


# ===== Function: decimate_with_feedback =====
def decimate_with_feedback(obj, max_attempts=6, quality="medium", hausdorff_threshold=0.01):
    """
    Iteratively decimate mesh while controlling quality via Hausdorff distance.
    """
    if obj.type != 'MESH':
        raise ValueError("Object must be a mesh")
    
    polygon_target = {
        'high': 200000,
        'medium': 50000,
        'low': 10000
    }

    current_target = polygon_target[quality]

    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj

    for i in range(max_attempts):
        # Remove previous decimated object (if not first iteration)
        if i > 0:
            bpy.data.objects.remove(dec_obj, do_unlink=True)

        # Duplicate original
        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.duplicate()
        dec_obj = bpy.context.active_object
        dec_obj.name = f"{obj.name}_decimated"

        # Apply decimate
        mod = dec_obj.modifiers.new(name="Decimate", type='DECIMATE')
        mod.use_collapse_triangulate = True
        current_faces = len(dec_obj.data.polygons)
        mod.ratio = current_target / current_faces
        bpy.ops.object.modifier_apply(modifier=mod.name)

        # Measure Hausdorff
        dist = compute_hausdorff_distance(obj, dec_obj)

        if dist <= hausdorff_threshold:
            break  # Acceptable
        else:
            current_target = int(current_target * 1.5)

    return dec_obj


if __name__ == "__main__":
    args = parse_arguments()

    model = import_model(args.input_file)

    merge_vertices(model)

    bbox_diag = model.dimensions.length  # diagonal length of bounding box
    hausdorff_threshold = 0.001 * bbox_diag
    dec_obj = decimate_with_feedback(model, quality=args.quality, hausdorff_threshold=hausdorff_threshold)

    export_model(dec_obj, args.output_file)