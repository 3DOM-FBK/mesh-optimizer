import os
import cv2
import bpy
import sys
import argparse
import numpy as np


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


# ===== Function: bake_ambientOcclusion =====
def bake_ambientOcclusion(model, output_path, img_size=1024):
    """
    Bake an Ambient Occlusion (AO) map for a given Blender mesh object.

    This function creates a new image, assigns it to the object's material,
    sets up nodes if needed, and performs an AO bake using Cycles.

    Args:
        model (bpy.types.Object): The Blender mesh object to bake.
        output_path (str): Path where the baked AO image will be saved.
        img_size (int, optional): Resolution of the baked image in pixels (default: 1024).

    Notes:
        - If the object has no material, a new one is created automatically.
        - The output image is saved in PNG format.
    """
    bpy.ops.object.select_all(action='DESELECT')
    model.select_set(True)
    bpy.context.view_layer.objects.active = model

    img = bpy.data.images.new("AO_Bake", width=img_size, height=img_size)

    if not model.data.materials:
        mat = bpy.data.materials.new(name="AO_Mat")
        model.data.materials.append(mat)
    else:
        mat = model.data.materials[0]

    mat.use_nodes = True
    nodes = mat.node_tree.nodes

    tex_node = nodes.new("ShaderNodeTexImage")
    tex_node.image = img
    mat.node_tree.nodes.active = tex_node

    bpy.context.scene.render.engine = 'CYCLES'
    bpy.context.scene.cycles.bake_type = 'AO'

    bpy.ops.object.bake(type='AO')

    img.filepath_raw = output_path
    img.file_format = 'PNG'
    img.save()



if __name__ == "__main__":
    args = parse_arguments()

    if (args.basecolor_img != "None"):
        generate_roughness(args.basecolor_img, "/tmp/roughness.png")

    model = import_model(args.input_file)
    bake_ambientOcclusion(model, "/tmp/ambientOcclusion.png", args.bake_image_size)
