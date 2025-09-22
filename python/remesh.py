import bpy
import os
import sys
import argparse
import bmesh
import subprocess
import trimesh
import xatlas
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
    parser.add_argument('-s', '--bake_image_size', type=int, default=512, help='Size of baked textures (default = 512)')
    parser.add_argument('-b', '--basecolor_img', type=str, help='Basecolor image to apply on high resolution mesh')

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


# ===== Function: clear_scene =====
def clear_scene():
    """
    Remove all objects from the current Blender scene.

    This function selects all objects in the active scene and deletes them,
    effectively clearing the scene of meshes, cameras, lights, and other objects.

    Notes:
        - Does not remove other data blocks such as materials, textures, or images.
        - Operates on the currently active view layer.
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
        filepath (str): Full path to the 3D model file to import.

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


# ===== Function: create_bake_image =====
def create_bake_image(name, size=2048):
    """
    Create a new blank image in Blender for baking purposes.

    Args:
        name (str): Name of the image to create.
        size (int, optional): Width and height of the square image in pixels (default: 2048).

    Returns:
        bpy.types.Image: The newly created Blender image object.
    """
    img = bpy.data.images.new(name=name, width=size, height=size)


# ===== Function: compose_node_material =====
def compose_node_material(obj):
    """
    Automatically create and assign a material with nodes to a Blender mesh object
    based on available diffuse, normal, and ambient occlusion images.

    The function searches the Blender file for images with names containing keywords:
    - Diffuse/BaseColor/Albedo → connected to Base Color
    - Normal → connected through a Normal Map node
    - AO/AmbientOcclusion → optionally connected to a "gltf settings" node group

    Args:
        obj (bpy.types.Object): The Blender mesh object to assign the composed material to.

    Notes:
        - If the object has existing materials, they are cleared before assignment.
        - Normal and AO textures are set to Non-Color data.
        - A new material node tree is created for the object.
        - If a node group named "gltf settings" does not exist, it will be created.
    """
    diffuse_img = None
    normal_img = None
    ao_img = None

    for img in bpy.data.images:
        name = img.name.lower()
        if not diffuse_img and ("diffuse" in name or "basecolor" in name or "albedo" in name):
            diffuse_img = img
        elif not normal_img and "normal" in name:
            normal_img = img
        elif not ao_img and ("ao" in name or "ambientocclusion" in name):
            ao_img = img

    mat = bpy.data.materials.new(name="AutoBakeMaterial")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    output = nodes.new('ShaderNodeOutputMaterial')
    principled = nodes.new('ShaderNodeBsdfPrincipled')
    links.new(principled.outputs['BSDF'], output.inputs['Surface'])

    if diffuse_img:
        tex_diff = nodes.new('ShaderNodeTexImage')
        tex_diff.image = diffuse_img
        tex_diff.label = "Diffuse"
        tex_diff.name = "DiffuseTexture"
        tex_diff.location = (-600, 300)
        links.new(tex_diff.outputs['Color'], principled.inputs['Base Color'])

    if normal_img:
        tex_norm = nodes.new('ShaderNodeTexImage')
        tex_norm.image = normal_img
        tex_norm.image.colorspace_settings.name = 'Non-Color'
        tex_norm.label = "Normal"
        tex_norm.name = "NormalTexture"
        tex_norm.location = (-600, -200)

        norm_map = nodes.new('ShaderNodeNormalMap')
        norm_map.location = (-300, -200)
        links.new(tex_norm.outputs['Color'], norm_map.inputs['Color'])
        links.new(norm_map.outputs['Normal'], principled.inputs['Normal'])

    if ao_img:
        tex_ao = nodes.new('ShaderNodeTexImage')
        tex_ao.image = ao_img
        tex_ao.label = "AO"
        tex_ao.name = "AOTexture"
        tex_ao.location = (-600, 0)
        tex_ao.image.colorspace_settings.name = 'Non-Color'

        if "gltf settings" in bpy.data.node_groups:
            group = bpy.data.node_groups["gltf settings"]
        else:
            group = bpy.data.node_groups.new("gltf settings", 'ShaderNodeTree')

        group.interface.new_socket(name='Occlusion', in_out='INPUT', socket_type='NodeSocketFloat',)

        group_node = nodes.new('ShaderNodeGroup')
        group_node.node_tree = group
        group_node.location = (0, -100)
        group_node.label = "gltf settings"

        links.new(tex_ao.outputs['Color'], group_node.inputs['Occlusion'])

    obj.data.materials.clear()
    obj.data.materials.append(mat)


# ===== Function: adaptive_cage_distance =====
#
# --> Bisogna lavorare su questa funzione, non calcola bene il valore di cage !!!
#
def adaptive_cage_distance(high_obj, low_obj, sample_size=500, factor=1.5, max_ray_dist=1):
    """
    Estimate an adaptive cage distance for a low-poly mesh based on a high-poly mesh.

    This function samples vertices on the low-poly object, casts rays along their normals
    (and opposite) against the high-poly mesh to measure distances, computes an average,
    and multiplies it by a factor to determine a suitable cage distance for baking.

    Args:
        high_obj (bpy.types.Object): The high-resolution source mesh.
        low_obj (bpy.types.Object): The low-resolution target mesh.
        sample_size (int, optional): Number of vertices to sample from the low-poly mesh (default: 500).
        factor (float, optional): Multiplier applied to the average distance to compute cage size (default: 1.5).
        max_ray_dist (float, optional): Maximum distance for ray casting (default: 1).

    Returns:
        float: Calculated cage distance, clamped between 0.005 and 0.05.

    Notes:
        - If no valid distances are found, a default small value (0.01) is returned.
        - Uses Blender's BVHTree for ray casting.
        - Clears evaluated meshes after computation to free memory.
    """
    depsgraph = bpy.context.evaluated_depsgraph_get()

    high_eval = high_obj.evaluated_get(depsgraph)
    low_eval = low_obj.evaluated_get(depsgraph)

    try:
        bvh = BVHTree.FromObject(high_eval, depsgraph)
    except Exception as e:
        return 0.01

    verts = low_eval.data.vertices
    indices = random.sample(range(len(verts)), min(sample_size, len(verts)))

    total = 0.0
    count = 0

    for i in indices:
        v = verts[i]
        pw = low_obj.matrix_world @ v.co
        normal = low_obj.matrix_world.to_3x3() @ v.normal
        normal.normalize()

        hit_pos_1 = bvh.ray_cast(pw, normal, max_ray_dist)[0]
        hit_pos_2 = bvh.ray_cast(pw, -normal, max_ray_dist)[0]

        d1 = (hit_pos_1 - pw).length if hit_pos_1 else None
        d2 = (hit_pos_2 - pw).length if hit_pos_2 else None

        dist = None
        if d1 and d2:
            dist = min(d1, d2)
        elif d1:
            dist = d1
        elif d2:
            dist = d2

        if dist:
            total += dist
            count += 1

    low_eval.to_mesh_clear()
    high_eval.to_mesh_clear()

    if count == 0:
        return 0.01

    avg = total / count
    cage = avg * factor
    cage = max(min(cage, 0.05), 0.005)  # Sicurity Clamp
    return cage


# ===== Function: bake_texture =====
def bake_texture(high_obj, low_obj, bake_type, cage_dist):
    """
    Bake a texture from a high-poly mesh onto a low-poly mesh in Blender using Cycles.

    The function selects both objects, finds the appropriate image texture node
    on the low-poly material based on the bake type, and performs a selected-to-active bake.

    Args:
        high_obj (bpy.types.Object): The high-resolution source mesh.
        low_obj (bpy.types.Object): The low-resolution target mesh.
        bake_type (str): Type of bake to perform. Supported: 'DIFFUSE', 'AO', 'NORMAL'.
        cage_dist (float): Cage extrusion distance for the bake.

    Returns:
        bpy.types.Image: The baked image from the corresponding image texture node.

    Raises:
        ValueError: If the low-poly object has no node-based material or if no corresponding image node is found.

    Notes:
        - The low-poly mesh must have a material with an image texture node corresponding to the bake type.
        - For 'DIFFUSE' bakes, only the color pass is used.
        - Uses the selected-to-active baking method.
    """
    bpy.context.scene.render.engine = 'CYCLES'

    bpy.ops.object.select_all(action='DESELECT')
    high_obj.select_set(True)
    low_obj.select_set(True)
    bpy.context.view_layer.objects.active = low_obj

    mat = low_obj.active_material
    if not mat or not mat.use_nodes:
        raise ValueError("Low object must have a node-based material assigned.")

    node_tree = mat.node_tree
    image_node = None

    for node in node_tree.nodes:
        if isinstance(node, bpy.types.ShaderNodeTexImage):
            node_name = node.name.lower()
            if bake_type == 'DIFFUSE' and 'diffuse' in node_name:
                image_node = node
                break
            elif bake_type == 'AO' and 'ao' in node_name:
                image_node = node
                break
            elif bake_type == 'NORMAL' and 'normal' in node_name:
                image_node = node
                break

    if image_node is None:
        raise ValueError(f"No image texture node found for bake type '{bake_type}'")

    node_tree.nodes.active = image_node

    
    if bake_type == 'DIFFUSE' and 'diffuse' in node_name:
        bake_settings = bpy.context.scene.render.bake
        bake_settings.use_pass_color = True
        bake_settings.use_pass_direct = False
        bake_settings.use_pass_indirect = False

    bpy.ops.object.bake(type=bake_type,
                        use_selected_to_active=True,
                        cage_extrusion=cage_dist)

    return image_node.image


# ===== Function: remesh_geometry =====
def remesh_geometry(input_path, output_path):
    """
    Perform remeshing on a 3D model using an external C++ executable.

    Args:
        input_path (str): Path to the input 3D model file.
        output_path (str): Path where the remeshed output will be saved.

    Returns:
        bool: True if the remeshing process succeeded, False otherwise.

    Notes:
        - Uses the external remeshing executable located at '/opt/remesh'.
        - The function relies on `run_cpp_executable` to run the external tool.
    """
    remesh_exec = os.path.abspath('/opt/remesh')
    res = run_cpp_executable(remesh_exec, [input_path, output_path])

    return res


# ===== Function: gen_uv =====
def gen_uv(model):
    """
    Generate UV coordinates for a 3D mesh using xatlas.

    Args:
        model (str): Path to the input 3D model file.

    Returns:
        bool: True if UVs were successfully generated and exported, False otherwise.

    Notes:
        - Loads the mesh with trimesh and uses xatlas to parameterize the UVs.
        - UVs are exported back to the same model file if generation is successful.
        - Returns False if no valid UVs could be generated.
    """
    mesh = trimesh.load_mesh(model)
    vmapping, indices, uvs = xatlas.parametrize(mesh.vertices, mesh.faces)

    if uvs is not None and len(uvs) > 0 and not (uvs == 0).all():
        xatlas.export(model, mesh.vertices[vmapping], indices, uvs)
        return True
    else:
        return False


# ===== Function: export_model =====
def export_model(obj, filepath):
    """
    Export a Blender mesh object to a specified file format.

    Currently, only OBJ format is supported.

    Args:
        obj (bpy.types.Object): The Blender mesh object to export.
        filepath (str): The path (including filename and extension) where the object will be exported.

    Raises:
        TypeError: If the provided object is not a mesh.
        ValueError: If the file extension is unsupported.

    Notes:
        - The function deselects all other objects before exporting.
        - Only the selected object is exported.
        - Materials are not exported for OBJ format.
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
    else:
        raise ValueError(f"Unsupported format: {ext}")


# ===== Function: save_image =====
def save_image(image, path):
    """
    Save a Blender image to disk in PNG format.

    Args:
        image (bpy.types.Image): The Blender image object to save.
        path (str): Full file path where the image will be saved.

    Notes:
        - The image format is set to PNG regardless of the original format.
        - Overwrites the file if it already exists at the specified path.
    """
    image.filepath_raw = path
    image.file_format = 'PNG'
    image.save()


# ===== Function: bake_texture =====
def run_bake_texture(baseColor_img, tex_folder, bake_image_size):
    """
    Bake textures from a high-resolution mesh onto a low-resolution mesh in Blender.

    This function imports high- and low-res models, optionally assigns a base color texture
    to the high-res model, merges vertices on the low-res model, applies smooth shading,
    creates bake images, sets up the node material, computes an adaptive cage distance, 
    performs normal and diffuse baking, saves the resulting textures, and exports the low-res model.

    Args:
        baseColor_img (str): Path to the base color image to assign to the high-res mesh.
        tex_folder (str): Folder where the baked textures will be saved.
        bake_image_size (int): Resolution for the bake images (e.g., 1024, 2048).

    Returns:
        bool: True if the baking process completed successfully, False if any error occurred.

    Notes:
        - Uses Blender's Cycles renderer for baking.
        - Handles normal and diffuse texture baking by default.
        - Saves baked images in PNG format.
        - Exports the low-res mesh to the same path as the high-res model.
        - Any failure during the process will return False.
    """
    try:
        high_res = "/tmp/model.obj"
        low_res = "/tmp/model_edit.obj"

        high_model = import_model(high_res)
        low_model = import_model(low_res)

        high_model.name = "HighRes"
        low_model.name = "LowRes"

        if os.path.isfile(baseColor_img):
            assign_texture_to_mesh(high_model, baseColor_img)
        
        merge_vertices(low_model)

        bpy.ops.object.shade_smooth()
        bake_types = {"normal": "NORMAL", "diffuse": "DIFFUSE"}
        for name in bake_types:
            create_bake_image(name, bake_image_size)
        compose_node_material(low_model)

        cage_dist = adaptive_cage_distance(high_model, low_model)
        for name, bake_type in bake_types.items():
            current_img = bake_texture(high_model, low_model, bake_type, cage_dist)
            save_image(current_img, os.path.join(tex_folder, f"{name}.png"))
        
        filepath = high_res
        export_model(low_model, filepath)

        return True
    except:
        return False
    

if __name__ == "__main__":
    args = parse_arguments()

    clear_scene()

    input_path = args.input_file
    root, ext = os.path.splitext(input_path)
    output_path = f"{root}_edit{ext}"

    tex_folder = "/tmp/"
    res_remesh = remesh_geometry(input_path, output_path)

    if res_remesh:
        res_uv = gen_uv(output_path)

        if res_uv:
            res_bake = run_bake_texture(args.basecolor_img, tex_folder, args.bake_image_size)

            if not res_bake:
                sys.exit(1)

        else:
            sys.exit(1)
    
    else:
        sys.exit(1)




