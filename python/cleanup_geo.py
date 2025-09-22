import bpy
import os
import sys
import argparse
import bmesh
import cv2


# ===== Function: parse_arguments =====
def parse_arguments():
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = []

    parser = argparse.ArgumentParser(description="Process 3D model baking parameters.")
    parser.add_argument('-i', '--input_file', type=str, required=True, help='Input file')
    parser.add_argument('-b', '--basecolor_img', type=str, help='Basecolor image to apply on high resolution mesh')
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
    Import a 3D model into Blender based on its file extension.

    Supported formats:
        - .obj : Wavefront OBJ
        - .fbx : Autodesk FBX
        - .ply : Polygon File Format

    Args:
        filepath (str): The full path to the 3D model file to import.

    Returns:
        bpy.types.Object: The first object that was selected after import.

    Raises:
        ValueError: If the file extension is not supported.
    """
    ext = os.path.splitext(filepath)[1].lower()
    if ext == ".obj":
        bpy.ops.wm.obj_import(filepath=filepath)
    elif ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=filepath)
    elif ext == ".ply":
        bpy.ops.wm.ply_import(filepath=filepath)
    else:
        raise ValueError(f"Unsupported format: {ext}")
    return bpy.context.selected_objects[0]


# ===== Function: export_model =====
def export_model(model):
    """
    Export a single Blender mesh object to OBJ format.

    This function selects only the specified mesh object, deselects everything else,
    and exports it to a predefined filepath (/tmp/model.obj) in OBJ format.

    Args:
        model (bpy.types.Object): The Blender object to export. Must be of type 'MESH'.

    Raises:
        TypeError: If the provided object is not a mesh.
    """
    if model.type != 'MESH':
        raise TypeError(f"Object '{model.name}' is not a mesh.")
    
    # Deselect everything
    bpy.ops.object.select_all(action='DESELECT')

    # Select only the object we want to export
    model.select_set(True)
    bpy.context.view_layer.objects.active = model
    
    bpy.ops.wm.obj_export(
        filepath="/tmp/model.obj",
        export_selected_objects=True,
        export_materials=False
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


# ===== Function: compose_node_material =====
def prep_texture(input_path, output_path, width, height, interpolation=cv2.INTER_LINEAR):
    """
    Resize a texture image to the specified width and height and save it to a new path.

    Args:
        input_path (str): Path to the input image file.
        output_path (str): Path where the resized image will be saved.
        width (int): Target width in pixels.
        height (int): Target height in pixels.
        interpolation (int, optional): Interpolation method used by OpenCV (default: cv2.INTER_LINEAR).

    Raises:
        FileNotFoundError: If the input image file does not exist or cannot be read.
    """
    img = cv2.imread(input_path)

    if img is None:
        raise FileNotFoundError(f"Immagine non trovata: {input_path}")

    resized = cv2.resize(img, (width, height), interpolation=interpolation)

    cv2.imwrite(output_path, resized)


if __name__ == "__main__":
    args = parse_arguments()

    clear_scene()

    model = import_model(args.input_file)
    remove_loose_geometry(model)
    triangulate_object(model)
    export_model(model)

    if (args.basecolor_img != "None"):
        prep_texture(args.basecolor_img, os.path.join("/tmp", "diffuse.png"), args.bake_image_size, args.bake_image_size, interpolation=cv2.INTER_LINEAR)