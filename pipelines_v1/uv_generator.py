"""
UV Generation Pipeline using PartUV

This module provides UV unwrapping functionality for 3D meshes using the PartUV library.
It handles mesh preprocessing, UV generation, scale restoration, and optional UV packing.
"""

import os
import sys
import gc
import argparse
from pathlib import Path
from typing import Optional, Tuple
from dataclasses import dataclass

import numpy as np
import trimesh
import torch

# Import partuv from pip installation FIRST (before modifying sys.path)
# This ensures we use the compiled _core.so from the pip package
import partuv
from partuv.preprocess import preprocess, save_results

# Add PartUV source directory for preprocess_utils and pack modules
# These are not installed via pip but needed for the pipeline
if '/opt/partuv' not in sys.path:
    sys.path.append('/opt/partuv')

# Additional PartUV imports that need the source directory
from preprocess_utils.partfield_official.run_PF import PFInferenceModel
from pack.pack import pack_mesh


# ============================================================================
# Configuration
# ============================================================================

@dataclass
class UVGeneratorConfig:
    """Configuration for UV generation pipeline."""
    # PartUV config file path
    config_path: str = "/opt/partuv/config/config.yaml"
    
    # Preprocessing parameters
    sample_on_faces: int = 4
    sample_batch_size: int = 100_000
    merge_vertices_epsilon: float = 1e-7
    
    # UV generation parameters
    distortion_threshold: float = 1.25
    
    # Output options
    save_tree_file: bool = True
    save_processed_mesh: bool = True
    
    # Packing options
    pack_method: str = "none"  # "blender", "uvpackmaster", "none"
    save_visuals: bool = False
    
    # Output file names
    output_mesh_name: str = "final_components.obj"


# ============================================================================
# Mesh Transform Utilities
# ============================================================================

class MeshTransform:
    """Handles mesh bounding box transformations for scale preservation."""
    
    def __init__(self, vertices: np.ndarray):
        """
        Initialize transform parameters from mesh vertices.
        
        Args:
            vertices: Nx3 array of vertex positions
        """
        v_min = vertices.min(axis=0)
        v_max = vertices.max(axis=0)
        self.center = (v_min + v_max) * 0.5
        self.scale = (v_max - v_min).max()
    
    def restore_scale(self, vertices: np.ndarray) -> np.ndarray:
        """
        Restore original scale to normalized vertices.
        
        Args:
            vertices: Normalized vertex positions
            
        Returns:
            Vertices with original scale restored
        """
        current_center, current_scale = self._compute_params(vertices)
        
        if current_scale > 0:
            scale_factor = self.scale / current_scale
            return (vertices - current_center) * scale_factor + self.center
        return vertices
    
    @staticmethod
    def _compute_params(vertices: np.ndarray) -> Tuple[np.ndarray, float]:
        """Compute center and scale from vertices."""
        v_min = vertices.min(axis=0)
        v_max = vertices.max(axis=0)
        center = (v_min + v_max) * 0.5
        scale = (v_max - v_min).max()
        return center, scale


# ============================================================================
# UV Generator Pipeline
# ============================================================================

class UVGenerator:
    """
    UV Generation pipeline using PartUV.
    
    This class handles the complete workflow of:
    1. Loading and preprocessing the input mesh
    2. Running PartField for hierarchical part segmentation
    3. Generating UV coordinates with PartUV
    4. Restoring original mesh scale
    5. Optional UV packing
    """
    
    def __init__(
        self,
        config: Optional[UVGeneratorConfig] = None,
        device: str = "auto"
    ):
        """
        Initialize the UV generator.
        
        Args:
            config: Configuration for the pipeline
            device: Device for inference ("cuda", "cpu", or "auto")
        """
        self.config = config or UVGeneratorConfig()
        
        # Determine device
        if device == "auto":
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            self.device = device
        
        # Lazy-load the PartField model
        self._pf_model: Optional[PFInferenceModel] = None
    
    @property
    def pf_model(self) -> PFInferenceModel:
        """Lazy-load PartField model on first access."""
        if self._pf_model is None:
            print(f"Loading PartField model on {self.device}...")
            self._pf_model = PFInferenceModel(device=self.device)
        return self._pf_model
    
    def generate_uvs(
        self,
        mesh_path: str,
        output_path: str,
        hierarchy_path: Optional[str] = None,
        restore_scale: bool = True
    ) -> bool:
        """
        Generate UV coordinates for a mesh.
        
        Args:
            mesh_path: Path to input mesh file
            output_path: Directory to save output files
            hierarchy_path: Optional pre-computed hierarchy file
            restore_scale: Whether to restore original mesh scale
            
        Returns:
            True if successful, False otherwise
        """
        os.makedirs(output_path, exist_ok=True)
        
        # Clear GPU cache
        self._clear_gpu_cache()
        
        # Save original transform for scale restoration
        original_transform = None
        if restore_scale:
            original_transform = self._get_original_transform(mesh_path)
        
        try:
            # Run UV generation pipeline
            if hierarchy_path is None:
                final_parts, individual_parts = self._run_with_preprocessing(
                    mesh_path, output_path
                )
            else:
                final_parts, individual_parts = self._run_with_hierarchy(
                    mesh_path, hierarchy_path
                )
            
            # Save results
            save_results(output_path, final_parts, individual_parts)
            
            # Restore original scale if requested
            if restore_scale and original_transform:
                self._restore_output_scale(output_path, original_transform)
            
            # Print summary
            self._print_summary(final_parts, individual_parts)
            
            # Optional packing
            if self.config.pack_method in ["uvpackmaster", "blender"]:
                self._pack_uvs(output_path)
            
            return True
            
        except Exception as e:
            print(f"Error during UV generation: {e}")
            raise
        finally:
            # Cleanup
            self._cleanup()
    
    def _run_with_preprocessing(
        self,
        mesh_path: str,
        output_path: str
    ) -> Tuple:
        """Run pipeline with PartField preprocessing."""
        print("Running preprocessing with PartField...")
        
        mesh, tree_filename, tree_dict, preprocess_times = preprocess(
            mesh_path,
            self.pf_model,
            output_path,
            save_tree_file=self.config.save_tree_file,
            save_processed_mesh=self.config.save_processed_mesh,
            sample_on_faces=self.config.sample_on_faces,
            sample_batch_size=self.config.sample_batch_size,
            merge_vertices_epsilon=self.config.merge_vertices_epsilon
        )
        
        print(f"Mesh after preprocessing: {mesh.faces.shape[0]} faces, {mesh.vertices.shape[0]} vertices")
        
        final_parts, individual_parts = partuv.pipeline_numpy(
            V=mesh.vertices,
            F=mesh.faces,
            tree_dict=tree_dict,
            configPath=self.config.config_path,
            threshold=self.config.distortion_threshold
        )
        
        return final_parts, individual_parts
    
    def _run_with_hierarchy(
        self,
        mesh_path: str,
        hierarchy_path: str
    ) -> Tuple:
        """Run pipeline with pre-computed hierarchy."""
        print(f"Using pre-computed hierarchy: {hierarchy_path}")
        
        final_parts, individual_parts = partuv.pipeline(
            tree_filename=hierarchy_path,
            mesh_filename=mesh_path,
            configPath=self.config.config_path,
            threshold=self.config.distortion_threshold
        )
        
        return final_parts, individual_parts
    
    def _get_original_transform(self, mesh_path: str) -> MeshTransform:
        """Load mesh and compute original transform parameters."""
        print("Computing original mesh transform...")
        mesh = trimesh.load(mesh_path, process=False, force='mesh')
        transform = MeshTransform(mesh.vertices)
        print(f"  Center: {transform.center}")
        print(f"  Scale: {transform.scale}")
        del mesh
        return transform
    
    def _restore_output_scale(
        self,
        output_path: str,
        original_transform: MeshTransform
    ):
        """Restore original scale to output mesh."""
        output_mesh_path = os.path.join(output_path, self.config.output_mesh_name)
        
        if not os.path.exists(output_mesh_path):
            print(f"Warning: Output mesh not found at {output_mesh_path}")
            return
        
        print("Restoring original scale...")
        mesh = trimesh.load(output_mesh_path, process=False)
        mesh.vertices = original_transform.restore_scale(mesh.vertices)
        mesh.export(output_mesh_path, file_type="obj")
        print(f"  Saved to {output_mesh_path}")
    
    def _pack_uvs(self, output_path: str):
        """Pack UV islands using specified method."""
        print(f"Packing UVs with {self.config.pack_method}...")
        try:
            pack_mesh(
                output_path,
                uvpackmaster=(self.config.pack_method == "uvpackmaster"),
                save_visuals=self.config.save_visuals
            )
        except Exception as e:
            print(f"Warning: UV packing failed: {e}")
    
    def _print_summary(self, final_parts, individual_parts):
        """Print pipeline results summary."""
        print("\n" + "="*50)
        print("UV Generation Complete")
        print("="*50)
        print(f"  Components: {final_parts.num_components}")
        print(f"  Max distortion: {final_parts.distortion:.4f}")
        print(f"  Individual parts: {len(individual_parts)}")
        
        if final_parts.num_components > 0:
            uv_coords = final_parts.getUV()
            print(f"  UV coordinates: {uv_coords.shape}")
        print("="*50 + "\n")
    
    def _clear_gpu_cache(self):
        """Clear GPU memory cache."""
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    
    def _cleanup(self):
        """Force garbage collection and clear GPU cache."""
        gc.collect()
        self._clear_gpu_cache()


# ============================================================================
# CLI Interface
# ============================================================================

def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Generate UV coordinates for 3D meshes using PartUV.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    
    parser.add_argument(
        "--mesh_path", "-i",
        type=str,
        required=True,
        help="Path to input mesh file (.obj, .glb, .gltf)"
    )
    
    parser.add_argument(
        "--output_path", "-o",
        type=str,
        default=None,
        help="Output directory (default: ./output/<mesh_name>)"
    )
    
    parser.add_argument(
        "--config_path", "-c",
        type=str,
        default="/opt/partuv/config/config.yaml",
        help="Path to PartUV config file"
    )
    
    parser.add_argument(
        "--hierarchy_path", "-hp",
        type=str,
        default=None,
        help="Optional pre-computed hierarchy file"
    )
    
    parser.add_argument(
        "--pack_method", "-p",
        type=str,
        default="none",
        choices=["blender", "uvpackmaster", "none"],
        help="UV packing method"
    )
    
    parser.add_argument(
        "--no_restore_scale",
        action="store_true",
        help="Don't restore original mesh scale"
    )
    
    parser.add_argument(
        "--save_visuals",
        action="store_true",
        help="Save visualization images after packing"
    )
    
    return parser.parse_args()


def main():
    """Main entry point."""
    args = parse_arguments()
    
    # Determine output path
    if args.output_path is None:
        mesh_name = Path(args.mesh_path).stem
        output_path = os.path.join("./output", mesh_name)
    else:
        mesh_name = Path(args.mesh_path).stem
        output_path = os.path.join(args.output_path, mesh_name)
    
    # Create config
    config = UVGeneratorConfig(
        config_path=args.config_path,
        pack_method=args.pack_method,
        save_visuals=args.save_visuals
    )
    
    # Run pipeline
    generator = UVGenerator(config=config)
    success = generator.generate_uvs(
        mesh_path=args.mesh_path,
        output_path=output_path,
        hierarchy_path=args.hierarchy_path,
        restore_scale=not args.no_restore_scale
    )
    
    if success:
        print("Done!")
    else:
        print("Pipeline failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()