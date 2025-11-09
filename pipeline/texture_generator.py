import os
import cv2
import bpy
import sys
import argparse
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
import cv2
import bmesh
from shutil import copyfile

# ===== Function: parse_arguments =====
def parse_arguments():
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = []

    parser = argparse.ArgumentParser(description="Process 3D model baking parameters.")
    parser.add_argument('--high_path', type=str, required=True, help='Input high model')
    parser.add_argument('--low_path', type=str, required=True, help='Input low model')
    parser.add_argument('-o', '--output_dir', type=str, required=True, help='Output dir')
    parser.add_argument('-s', '--image_size', type=int, default=512, help='Size of baked textures (default = 512)')

    return parser.parse_args(argv)


# ===== Function: generate_roughness =====
def generate_roughness(baseColor_img, output_path):
    """
    Generate a roughness map from a base color image.

    This function converts the input image to grayscale, inverts it, normalizes the values,
    and applies a minimum roughness threshold to produce a roughness map suitable for PBR workflows.

    Args:
        baseColor_img (str): Path to the input base color image.
        output_path (str): Path where the generated roughness map will be saved.

    Notes:
        - The output is an 8-bit grayscale image.
        - min_val sets the minimum roughness value (default: 0.05).
    """
    img = cv2.imread(baseColor_img)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    img = cv2.bitwise_not(gray)

    roughness = np.absolute(img)

    # Normalize 0-255
    roughness = cv2.normalize(roughness, None, 0, 255, cv2.NORM_MINMAX)
    roughness = np.uint8(roughness)

    min_val = 0.05
    roughness_ramped = min_val + (1 - min_val) * roughness
    roughness_ramped = np.uint8(roughness_ramped)

    cv2.imwrite(output_path, roughness_ramped)


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


# ===== Function: import_model =====
def import_model(filepath):
    """
    Import a 3D model into Blender based on its file extension.

    Supported formats:
        - .glb/.gltf

    Args:
        filepath (str): Full path to the 3D model file to import.

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


# ===== Function: create_bake_image =====
def create_bake_image(name, size=512):
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

    if bake_type == 'AO' and 'ao' in node_name:
        bpy.ops.object.bake(type=bake_type,
                            use_selected_to_active=False,
                            cage_extrusion=cage_dist)
    else:
        bpy.ops.object.bake(type=bake_type,
                            use_selected_to_active=True,
                            cage_extrusion=cage_dist)

    return image_node.image


# ===== Function: calculate_optimal_cage_distance =====
def calculate_optimal_cage_distance(
    low_poly_obj: bpy.types.Object,
    high_poly_obj: bpy.types.Object,
    percentile: float = 95.0,
    sample_count: int = 10000,
    safety_margin: float = 1.2
) -> dict:
    """
    Calculate optimal cage distance for baking between low and high poly models.
    
    Args:
        low_poly_obj: Low poly mesh object
        high_poly_obj: High poly mesh object
        percentile: Percentile of distances to use (default: 95.0)
                   Use 95-99 to avoid extreme outliers
        sample_count: Number of sample points to use (default: 1000)
                     Use more for better accuracy, fewer for speed
        safety_margin: Multiplier for final distance (default: 1.2)
                      Adds 20% safety margin to avoid artifacts
    
    Returns:
        Dictionary with:
        - suggested_distance: Recommended cage distance
        - min_distance: Minimum distance found
        - max_distance: Maximum distance found
        - mean_distance: Average distance
        - median_distance: Median distance
        - percentile_distance: Distance at specified percentile
    """
    
    # Get mesh data
    low_mesh = low_poly_obj.data
    high_mesh = high_poly_obj.data
    
    # Apply transformations
    low_matrix = low_poly_obj.matrix_world
    high_matrix = high_poly_obj.matrix_world
    
    # Build BVH tree for high poly mesh
    bm_high = bmesh.new()
    bm_high.from_mesh(high_mesh)
    bm_high.transform(high_matrix)
    bvh_high = BVHTree.FromBMesh(bm_high)
    
    # Sample points from low poly mesh
    bm_low = bmesh.new()
    bm_low.from_mesh(low_mesh)
    bm_low.transform(low_matrix)
    
    # Get vertices to sample
    vertices = [v.co for v in bm_low.verts]
    
    # If too many vertices, randomly sample
    if len(vertices) > sample_count:
        indices = np.random.choice(len(vertices), sample_count, replace=False)
        vertices = [vertices[i] for i in indices]
    
    # Calculate distances
    distances = []
    for vert in vertices:
        # Find closest point on high poly
        location, normal, index, distance = bvh_high.find_nearest(vert)
        if location is not None:
            distances.append(distance)
    
    # Clean up
    bm_low.free()
    bm_high.free()
    
    if not distances:
        raise ValueError("No valid distances found between meshes")
    
    # Calculate statistics
    distances = np.array(distances)
    min_dist = float(np.min(distances))
    max_dist = float(np.max(distances))
    mean_dist = float(np.mean(distances))
    median_dist = float(np.median(distances))
    percentile_dist = float(np.percentile(distances, percentile))
    
    # Suggested distance with safety margin
    suggested = percentile_dist * safety_margin
    
    return {
        'suggested_distance': suggested,
        'min_distance': min_dist,
        'max_distance': max_dist,
        'mean_distance': mean_dist,
        'median_distance': median_dist,
        'percentile_distance': percentile_dist,
        'percentile_used': percentile,
        'safety_margin': safety_margin
    }


# ===== Function: calculate_cage_distance_bidirectional =====
def calculate_cage_distance_bidirectional(
    low_poly_obj: bpy.types.Object,
    high_poly_obj: bpy.types.Object,
    percentile: float = 95.0,
    sample_count: int = 10000,
    safety_margin: float = 1.2
) -> dict:
    """
    Calculate cage distance considering both directions (low->high and high->low).
    More accurate for complex overlapping meshes.
    
    Args:
        Same as calculate_optimal_cage_distance
    
    Returns:
        Dictionary with bidirectional statistics
    """
    
    # Calculate low -> high
    result_lh = calculate_optimal_cage_distance(
        low_poly_obj, high_poly_obj, percentile, sample_count, safety_margin
    )
    
    # Calculate high -> low
    result_hl = calculate_optimal_cage_distance(
        high_poly_obj, low_poly_obj, percentile, sample_count, safety_margin
    )
    
    # Take maximum to ensure both meshes are covered
    suggested = max(result_lh['suggested_distance'], result_hl['suggested_distance'])
    
    return suggested

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


# ===== Function: export_model =====
def export_model(model, filepath, use_selection=True):
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

    bpy.ops.export_scene.gltf(
        filepath=filepath,
        export_format='GLB',
        use_selection=use_selection
    )


# ===== Function: bake_texture =====
def run_bake_texture(low_model, high_model, cage_dist, out_dir, bake_image_size):
    high_model.name = "HighRes"
    low_model.name = "LowRes"
    
    merge_vertices(low_model)

    bpy.ops.object.shade_smooth()
    bake_types = {"normal": "NORMAL", "diffuse": "DIFFUSE", "ao": "AO"}
    for name in bake_types:
        create_bake_image(name, bake_image_size)
    compose_node_material(low_model)

    tex_dir = os.path.join(out_dir, "tex")
    for name, bake_type in bake_types.items():
        current_img = bake_texture(high_model, low_model, bake_type, cage_dist*2)
        save_image(current_img, os.path.join(tex_dir, f"{name}.png"))


# ===== Function: export_diffuse_texture =====
def export_diffuse_texture(obj, output_dir):
    """
    Export the diffuse texture (Base Color) of the given object's material to a specific folder.
    The exported file will always be named 'tmp_diffuse.<ext>'.
    
    Args:
        obj (bpy.types.Object): The Blender object to process.
        output_dir (str): Folder path where the texture will be exported.
    
    Returns:
        bool: True if a diffuse texture was found and exported, False otherwise.
    """
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    if not obj or not obj.data.materials:
        print(f"[{obj.name}] No materials found.")
        return False

    for mat in obj.data.materials:
        if not mat or not mat.use_nodes:
            continue

        # Look for an Image Texture node connected to Base Color
        for node in mat.node_tree.nodes:
            if node.type == 'TEX_IMAGE':
                for link in node.outputs[0].links:
                    target = link.to_node
                    if target.type == 'BSDF_PRINCIPLED':
                        base_color_input = target.inputs.get('Base Color')
                        if base_color_input and base_color_input.is_linked and base_color_input.links[0].from_node == node:
                            image = node.image
                            if image is None:
                                return False

                            src_path = bpy.path.abspath(image.filepath)
                            if not os.path.exists(src_path):
                                return False

                            # Keep the same file extension
                            ext = os.path.splitext(src_path)[1]
                            dst_path = os.path.join(output_dir, f"tmp_diffuse{ext}")

                            copyfile(src_path, dst_path)
                            return True
    print(f"[{obj.name}] No diffuse texture found.")
    return False


def apply_roughness_texture(model_obj, image_path):
    """
    Load an image from disk and connect it to the Roughness input
    of the Principled BSDF shader for the model's material.

    Args:
        model_obj (bpy.types.Object): The object whose material will be modified.
        image_path (str): Path to the roughness texture image.

    Returns:
        bool: True if successful, False otherwise.
    """
    if not os.path.exists(image_path):
        return False

    if not model_obj or model_obj.type != 'MESH':
        return False

    if not model_obj.data.materials:
        return False

    mat = model_obj.data.materials[0]
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links

    bsdf = next((n for n in nodes if n.type == "BSDF_PRINCIPLED"), None)
    if bsdf is None:
        return False

    tex_node = nodes.new("ShaderNodeTexImage")
    tex_node.image = bpy.data.images.load(image_path)
    tex_node.label = "Roughness Texture"
    tex_node.name = "Roughness_Texture"

    links.new(tex_node.outputs["Color"], bsdf.inputs["Roughness"])

    return True

if __name__ == "__main__":
    args = parse_arguments()

    out_dir = os.path.join(args.output_dir, "tex")
    os.makedirs(out_dir, exist_ok=True)

    # Reset scene to avoid duplicate data
    bpy.ops.wm.read_factory_settings(use_empty=True)

    # Import models - High and Low
    high_model = import_model(args.high_path)
    low_model = import_model(args.low_path)

    # Compute optimal cage distance
    cage_distance = calculate_cage_distance_bidirectional(high_model, low_model)

    # Bake textures
    run_bake_texture(low_model, high_model, cage_distance, args.output_dir, args.image_size)

    # Generate Simple Roughness Map
    if (export_diffuse_texture(low_model, out_dir)):
        generate_roughness(os.path.join(out_dir,  "tmp_diffuse.png"), os.path.join(out_dir,  "roughness.png"))
        os.remove(os.path.join(out_dir,  "tmp_diffuse.png"))
        apply_roughness_texture(low_model, os.path.join(out_dir,  "roughness.png"))
    
    # Export final model
    filepath = os.path.join(args.output_dir, "mesh.glb")
    export_model(low_model, filepath, use_selection=True)