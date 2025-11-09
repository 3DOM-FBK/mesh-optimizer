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
    parser.add_argument('-b', '--basecolor_img', default="None", type=str, help='Basecolor image to apply on high resolution mesh')
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
        - .glb/.gltf : GL Transmission Format

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
    elif ext in [".glb", ".gltf"]:
        bpy.ops.import_scene.gltf(filepath=filepath, merge_vertices=True)
    else:
        raise ValueError(f"Unsupported format: {ext}")
    return bpy.context.selected_objects[0]


# ===== Function: assign_texture_to_mesh =====
def assign_texture_to_mesh(obj, image_path):
    """
    Assign a texture image to a Blender mesh object using a new Principled BSDF material.

    This function creates a new material with nodes, loads the specified image,
    connects it to the Base Color of a Principled BSDF shader, and assigns the material to the mesh.

    Args:
        obj (bpy.types.Object): The Blender mesh object to assign the texture to.
        image_path (str): Path to the image file to use as a texture.

    Raises:
        TypeError: If the provided object is not a mesh.
        RuntimeError: If the image cannot be loaded from the specified path.
    """
    # Ensure the object is a mesh
    if obj.type != 'MESH':
        raise TypeError("Object must be a mesh")

    # Create a new material
    mat = bpy.data.materials.new(name="TextureMaterial")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links

    # Clear default nodes
    for node in nodes:
        nodes.remove(node)

    # Create nodes
    output_node = nodes.new(type='ShaderNodeOutputMaterial')
    output_node.location = (400, 0)

    bsdf_node = nodes.new(type='ShaderNodeBsdfPrincipled')
    bsdf_node.location = (200, 0)

    tex_node = nodes.new(type='ShaderNodeTexImage')
    tex_node.location = (0, 0)

    # Load image
    try:
        image = bpy.data.images.load(image_path)
    except:
        raise RuntimeError(f"Cannot load image at {image_path}")
    tex_node.image = image

    # Connect nodes
    links.new(tex_node.outputs['Color'], bsdf_node.inputs['Base Color'])
    links.new(bsdf_node.outputs['BSDF'], output_node.inputs['Surface'])

    # Assign material to object
    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)


# ===== Function: export_model =====
def export_model(model):
    """
    Export a single Blender mesh object to GLB format.

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

    # Export to GLB format (optional)
    bpy.ops.export_scene.gltf(
        filepath="/tmp/model.glb",
        use_selection=True
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

    print(f"Combined mesh created: {combined_mesh.name}")
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


# ===== Function: export_diffuse_texture =====
def export_diffuse_texture(obj, export_dir):
    """
    Export diffuse texture from input geometry
    """
    if not obj or not obj.data.materials:
        print(f"No material found {obj.name}")
        return None

    for mat in obj.data.materials:
        if not mat.use_nodes:
            continue

        bsdf = None
        for node in mat.node_tree.nodes:
            if node.type == 'BSDF_PRINCIPLED':
                bsdf = node
                break

        if not bsdf:
            continue

        input_basecolor = bsdf.inputs.get("Base Color")
        if input_basecolor and input_basecolor.is_linked:
            from_node = input_basecolor.links[0].from_node
            if from_node.type == 'TEX_IMAGE' and from_node.image:
                image = from_node.image
                tex_name = "diffuse.png"
                export_path = os.path.join(export_dir, tex_name)
                image.save_render(export_path)

                prep_texture(export_path, os.path.join("/tmp", "diffuse.png"), args.bake_image_size, args.bake_image_size, interpolation=cv2.INTER_LINEAR)
                return export_path

    print(f"No Diffuse Texture found {obj.name}")
    return None


# ===== Function: main =====
if __name__ == "__main__":
    args = parse_arguments()

    clear_scene()

    model = import_model(args.input_file)
    
    ext = os.path.splitext(args.input_file)[1].lower()
    if ext in [".glb", ".gltf"]:
        try:
            combined = flatten_and_join(model.name, merge_vertices_threshold=0.001)
            model = combined
        except:
            print ("--> no root")
    
    select_non_manifold_and_merge(model)
    remove_loose_geometry(model)
    triangulate_object(model)

    if (args.basecolor_img != "None"):
        assign_texture_to_mesh(model, args.basecolor_img)

    export_model(model)

    export_diffuse_texture(model, "/tmp")