import os
import bpy
import argparse
import sys
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
    parser.add_argument('-s', '--bake_image_size', type=int, default=512, help='Size of baked textures (default = 512)')

    return parser.parse_args(argv)


# ===== Function: clear_scene =====
def clear_scene():
    """
    Remove all objects from the current Blender scene.
    """
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)


# ===== Function: import_model =====
def import_model(filepath):
    """
    Import a 3D model (.obj or .glb/.gltf) into Blender.
    
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


# ===== Function: export_model_glb =====
def export_model_glb(model, dir_path, use_selection=True):
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

    filepath = os.path.join(dir_path, "temp_model.glb")
    
    bpy.ops.export_scene.gltf(
        filepath=filepath,
        export_format='GLB',
        use_selection=use_selection
    )


# ===== Function: remove_loose_geometry =====
def remove_loose_geometry(obj):
    """
    Remove all loose geometry from a Blender mesh object.

    This function deletes vertices that are not connected to any edges
    and edges that are not connected to any faces, effectively cleaning
    up unreferenced or floating geometry in the mesh.

    Args:
        obj (bpy.types.Object): The Blender object to clean. Must be of type 'MESH'.

    Raises:
        TypeError: If the provided object is not a mesh.
    """
    if obj.type != 'MESH':
        raise TypeError(f"Object '{obj.name}' is not a mesh.")

    # Ensure we're in Object Mode
    bpy.ops.object.mode_set(mode='OBJECT')
    
    # Make sure object is active
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)

    # Enter Edit Mode to operate with BMesh
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='DESELECT')
    bpy.ops.mesh.select_mode(type='VERT')

    # Switch to BMesh for precise selection
    bpy.ops.object.mode_set(mode='OBJECT')
    mesh = obj.data
    bm = bmesh.new()
    bm.from_mesh(mesh)

    # Select loose verts (not connected to any edge)
    for v in bm.verts:
        if len(v.link_edges) == 0:
            v.select = True

    # Select loose edges (not connected to any face)
    for e in bm.edges:
        if len(e.link_faces) == 0:
            e.select = True

    # Apply changes back to mesh
    bm.to_mesh(mesh)
    bm.free()

    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.delete(type='VERT')  # deletes selected verts/edges
    bpy.ops.object.mode_set(mode='OBJECT')


# ===== Function: compose_node_material =====
def triangulate_object(obj):
    """
    Triangulate all faces of a Blender mesh object.

    This function converts all polygonal faces in the mesh to triangles,
    which can be useful for export, physics simulations, or rendering engines
    that require triangulated geometry.

    Args:
        obj (bpy.types.Object): The Blender object to triangulate. Must be of type 'MESH'.

    Raises:
        TypeError: If the provided object is not a mesh.
    """
    if obj.type != 'MESH':
        raise TypeError(f"Object '{obj.name}' is not a mesh.")

    # Ensure we are in object mode
    bpy.ops.object.mode_set(mode='OBJECT')
    
    # Make sure the object is active and selected
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)

    # Create a BMesh and triangulate
    mesh = obj.data
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    bm.to_mesh(mesh)
    bm.free()

    mesh.update()


# ===== Function: flatten_and_join =====
def flatten_and_join(root_name, merge_vertices_threshold=None):
    """
    Flatten the hierarchy under `root_name` by removing all parents,
    applying parent transforms, and joining all meshes into a single one.
    Optionally merge vertices by distance.
    """
    root = bpy.data.objects.get(root_name)
    if root is None:
        raise ValueError(f"Root object '{root_name}' not found")

    meshes = [obj for obj in root.children_recursive if obj.type == 'MESH']
    if not meshes:
        raise ValueError("No mesh objects found under the root")

    for mesh in meshes:
        mesh.matrix_world = root.matrix_world @ mesh.matrix_local
        mesh.parent = None  # scollega il parent
        mesh.matrix_parent_inverse.identity()

    # Deselect all
    bpy.ops.object.select_all(action='DESELECT')

    # Select all meshes
    for mesh in meshes:
        mesh.select_set(True)

    # Make one active
    bpy.context.view_layer.objects.active = meshes[0]

    # Join meshes
    bpy.ops.object.join()
    combined_mesh = bpy.context.view_layer.objects.active

    combined_mesh.matrix_world = root.matrix_world

    if merge_vertices_threshold is not None:
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.remove_doubles(threshold=merge_vertices_threshold)
        bpy.ops.object.mode_set(mode='OBJECT')
        combined_mesh.data.update()

    return combined_mesh


# ===== Function: select_non_manifold_and_merge =====
def select_non_manifold_and_merge(obj, merge_distance=0.001):
    # Assicurati che l'oggetto sia in modalità Object
    bpy.ops.object.mode_set(mode='OBJECT')
    
    # Seleziona l'oggetto e rendilo attivo
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    
    # Entra in Edit mode
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_mode(use_extend=False, use_expand=False, type='VERT')
    
    # Deseleziona tutto prima
    bpy.ops.mesh.select_all(action='DESELECT')
    
    # Seleziona i vertici non-manifold
    bpy.ops.mesh.select_non_manifold()
    
    # Applica Merge by Distance sui vertici selezionati
    bpy.ops.mesh.remove_doubles(threshold=merge_distance)
    
    # Torna in Object mode
    bpy.ops.object.mode_set(mode='OBJECT')


# ===== Function: join_all_meshes =====
def join_all_meshes():
    """
    Find all mesh objects in the current scene and join them into a single mesh.
    Returns the new joined object.
    """
    # Deselect everything
    bpy.ops.object.select_all(action='DESELECT')
    
    # Get all mesh objects
    mesh_objects = [obj for obj in bpy.context.scene.objects if obj.type == 'MESH']
    
    if not mesh_objects:
        raise ValueError("No mesh objects found in the scene.")
    
    # Select all mesh objects
    for obj in mesh_objects:
        obj.select_set(True)
    
    # Make the first one active (required for join)
    bpy.context.view_layer.objects.active = mesh_objects[0]
    
    # Join meshes
    bpy.ops.object.join()
    
    # Return the joined object
    return bpy.context.view_layer.objects.active


if __name__ == "__main__":
    """
    Main pipeline:
    - Import mesh (.obj or .glb)
    - If it's a .glb file, flatten and join meshes
    - Select and fix non-manifold geometry
    - Remove loose geometry
    - Triangulate the final object
    - Export as .glb
    """
    args = parse_arguments()

    # Clear scene
    clear_scene()

    # Import the model
    model = import_model(args.input_file)

    # Build output path in temp directory
    dataset_name = os.path.splitext(os.path.basename(args.input_file))[0]
    temp_dir = os.path.join("/tmp", dataset_name)
    os.makedirs(temp_dir, exist_ok=True)

    # Check if input file is GLB
    ext = os.path.splitext(args.input_file)[1].lower()
    if ext == ".glb":
        model = flatten_and_join(model.name)
    elif ext == ".obj":
        model = join_all_meshes()

    # Process geometry
    select_non_manifold_and_merge(model)
    remove_loose_geometry(model)
    triangulate_object(model)

    # Export final model
    export_model_glb(model, temp_dir, use_selection=True)