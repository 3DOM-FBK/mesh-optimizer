import os
import sys

# Add /opt/partuv to python path to access preprocess_utils and pack modules
if '/opt/partuv' not in sys.path:
    sys.path.append('/opt/partuv')

import numpy as np
import trimesh
import torch
from contextlib import contextmanager, redirect_stdout, redirect_stderr

# PartUV project imports
from preprocess_utils.partfield_official.run_PF import PFInferenceModel
import partuv
from partuv.preprocess import preprocess, save_results
from pack.eval_charts import evaluate_mesh
from pack.pack import pack_mesh


def get_mesh_transform_params(vertices: np.ndarray):
    """
    Compute the bounding box center and scale of a mesh.
    
    Returns:
        center: Center of the bounding box
        scale: Maximum extent of the bounding box
    """
    v_min = vertices.min(axis=0)
    v_max = vertices.max(axis=0)
    center = (v_min + v_max) * 0.5
    scale = (v_max - v_min).max()
    return center, scale


def restore_original_scale(output_path: str, original_center: np.ndarray, original_scale: float):
    """
    Restore the original scale to the output mesh.
    
    The PartUV pipeline normalizes the mesh to a unit cube. This function
    applies the inverse transformation to restore the original scale.
    
    Args:
        output_path: Path to the PartUV output directory
        original_center: Original mesh center
        original_scale: Original mesh scale (max bounding box extent)
    """
    final_mesh_path = os.path.join(output_path, "final_components.obj")
    
    if not os.path.exists(final_mesh_path):
        print(f"Warning: Could not find {final_mesh_path} to restore scale")
        return
    
    # Load the output mesh
    mesh = trimesh.load(final_mesh_path, process=False)
    
    # Get current transform params (should be normalized around [-1, 1] or similar)
    current_center, current_scale = get_mesh_transform_params(mesh.vertices)
    
    # Apply inverse normalization: first un-center, then un-scale
    # The PartUV output is typically centered at origin with unit scale
    # We need to scale it back to original size and translate to original position
    
    # Scale vertices to original size
    if current_scale > 0:
        scale_factor = original_scale / current_scale
        mesh.vertices = (mesh.vertices - current_center) * scale_factor + original_center
    
    # Save the corrected mesh
    mesh.export(final_mesh_path, file_type="obj")
    print(f"Restored original scale to {final_mesh_path}")




def partuv_pipeline(args, pf_model=None, save_output=True):
    mesh_path = args.mesh_path
    output_path = args.output_path
    config_path = args.config_path
    hierarchy_path = args.hierarchy_path
    
    os.makedirs(output_path, exist_ok=True)
    
    # Load original mesh to get transform parameters BEFORE any processing
    original_mesh = trimesh.load(mesh_path, process=False, force='mesh')
    original_center, original_scale = get_mesh_transform_params(original_mesh.vertices)
    print(f"Original mesh: center={original_center}, scale={original_scale}")
    del original_mesh  # Free memory
    
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


    if hierarchy_path is None:
        
        """
        Preprocessing the mesh.

        The code does the following:
        - Load the mesh.
        - Remove existing UV layers, if any.
        - Merge overlapping vertices, and set epsilon to None to disable merging.
        - Fix non-2-manifold meshes, if present.
        - (Optional) export the mesh to an .obj file.
        - Run PartField to generate the hierarchical part tree.

        Notable parameters:
        - sample_on_faces and sample_batch_size: sample points on faces to obtain PartField features for part assignment.
        The larger sample_on_faces is, the more robust the part assignment is, but more points will be sampled and thus it takes more time.
        The larger sample_batch_size is, the less time it takes, but the more GPU memory it uses. Reduce it if you run out of memory.
        - merge_vertices_epsilon: epsilon for merging overlapping vertices; set to None to disable merging.
        - save_processed_mesh: set to False to disable exporting the processed mesh.
        - save_tree_file: set to False to disable saving the tree file for reproducibility.
        - output_path: path where the processed mesh and tree file will be saved.
        """

        
        mesh, tree_filename, tree_dict, preprocess_times = preprocess(mesh_path, pf_model, output_path, save_tree_file=True, save_processed_mesh=True, sample_on_faces=4, sample_batch_size=100_000, merge_vertices_epsilon=1e-7)
        V = mesh.vertices
        F = mesh.faces
        configPath = config_path
        print(f"F.shape after preprocessing: {F.shape}, V.shape: {V.shape}")
        final_parts, individual_parts = partuv.pipeline_numpy(
            V=V,
            F=F,
            tree_dict=tree_dict,
            configPath=configPath,
            threshold=1.25
        )
    else:
        """
        Use the provided hierarchy file and processed mesh instead of running Preprocessing.
        """
        tree_filename = hierarchy_path
        mesh_filename = mesh_path
        configPath = config_path

        final_parts, individual_parts = partuv.pipeline(
            tree_filename=tree_filename,
            mesh_filename=mesh_filename,
            configPath=configPath,
            threshold=1.25
        )
        
        
    if save_output:
        save_results(output_path, final_parts, individual_parts)
        # Restore the original scale to the output mesh
        restore_original_scale(output_path, original_center, original_scale)
    print(f"Pipeline completed successfully!")
    print(f"Final parts: {final_parts.num_components} components")
    print(f"Final distortion: {final_parts.distortion}")
    print(f"Individual parts: {len(individual_parts)}")
    
    if final_parts.num_components > 0:
        uv_coords = final_parts.getUV()
        print(f"UV coordinates shape: {uv_coords.shape}")
        
        # You can also access individual components
        for i, component in enumerate(final_parts.components):
            print(f"Chart {i}: {component.F.shape[0]} faces, distortion: {component.distortion}")
        
    
    if args.pack_method in ["uvpackmaster", "blender"]:
        print(f"Starting to pack mesh with {args.pack_method} method")
        try:
            pack_mesh(output_path, uvpackmaster = args.pack_method == "uvpackmaster", save_visuals=args.save_visuals)
        except Exception as e:
            print(f"Error packing mesh with {args.pack_method} method: {e}")
            print(f"Skipping packing")
    
    # Force garbage collection
    import gc
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        
def main():
    import argparse

    parser = argparse.ArgumentParser(description="Run PartUV demo pipeline.")
    parser.add_argument("--mesh_path", type=str, default="/ariesdv0/zhaoning/workspace/partuv/swird_merge.obj", help="input mesh path")
    parser.add_argument("--config_path", "-cf", type=str, default="config/config.yaml", help="Config path.")
    parser.add_argument("--hierarchy_path", "-hp", type=str, default=None, help="(optional) Hierarchy path. If provided, it will be used directly in pipeline and skip the preprocessing (including PartField) entirely, make sure the mesh is preprocessed if the hierarchy file is provided.")
    parser.add_argument("--output_path", "-op", type=str, default=None, help="Output path.")
    parser.add_argument("--pack_method", "-pm", type=str, default="none", choices=["blender", "uvpackmaster", "none"], help="Pack method.")
    parser.add_argument("--save_visuals", "-sv", action="store_true", default=False, help="Save visuals (such as) after packing. This will be ignored if pack_method is 'none'.")
    args = parser.parse_args()

    # if args.output_path is None:
    #     mesh_name = os.path.basename(args.mesh_path).split(".")[0]
    #     args.output_path = os.path.join("./output", mesh_name)
    #     os.makedirs(args.output_path, exist_ok=True)
    
    mesh_name_base = os.path.basename(args.mesh_path).split(".")[0]
    if args.output_path is None:
        base_output_dir = "./output"
    else:
        base_output_dir = args.output_path
    
    args.output_path = os.path.join(base_output_dir, mesh_name_base)
    os.makedirs(args.output_path, exist_ok=True)
    
        
    pf_model = PFInferenceModel(device="cpu" if not torch.cuda.is_available() else "cuda")

    partuv_pipeline(args, pf_model, save_output=True)
    
    print("Done")


if __name__ == "__main__":
    main()