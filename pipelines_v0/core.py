"""
Core Pipeline Module

This module provides the main pipeline orchestration for 3D mesh processing.
It integrates scene management, I/O operations, and mesh clustering functionality.
"""

import sys
import logging
from pathlib import Path
from typing import List, Dict, Optional, Union
import bpy

# Add modules directory to path
MODULES_DIR = Path(__file__).parent / "modules"
sys.path.insert(0, str(MODULES_DIR))

# Import custom modules
from io_utils import import_model, export_model
from scene_manager import SceneManager, MeshClusterManager
from preprocess import ClusterPreprocessor


# ==============================================================================
# Logger Configuration
# ==============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ==============================================================================
# Main Pipeline Class
# ==============================================================================

class MeshPipeline:
    """
    Main pipeline class for 3D mesh processing.
    
    This class orchestrates the complete workflow:
    1. Scene cleanup
    2. Model import
    3. Material-based clustering
    4. Processing by cluster
    5. Export results
    """
    
    def __init__(self, input_file: Union[str, Path], verbose: bool = True):
        """
        Initialize the mesh pipeline.
        
        Args:
            input_file: Path to input GLB/GLTF file
            verbose: Enable verbose logging
        """
        self.input_file = Path(input_file)
        self.verbose = verbose
        
        if not self.input_file.exists():
            raise FileNotFoundError(f"Input file not found: {self.input_file}")
        
        # Set logging level
        if verbose:
            logger.setLevel(logging.DEBUG)
        else:
            logger.setLevel(logging.INFO)
        
        logger.info(f"Pipeline initialized for: {self.input_file.name}")
    
    
    def cleanup_scene(
        self,
        keep_camera: bool = False,
        keep_lights: bool = False
    ) -> None:
        """
        Clean up the Blender scene before processing.
        
        Args:
            keep_camera: Keep camera objects
            keep_lights: Keep light objects
        """
        logger.info("Cleaning up scene...")
        
        SceneManager.cleanup_keep_meshes(
            meshes_to_keep=[],
            remove_orphan_data=True
        )
        
        logger.info("✓ Scene cleanup completed")
    
    
    def import_mesh(self, merge_vertices: bool = True) -> List[bpy.types.Object]:
        """
        Import the mesh from the input file.
        
        Args:
            merge_vertices: Merge duplicate vertices on import
            
        Returns:
            List of imported mesh objects
        """
        logger.info(f"Importing mesh from: {self.input_file}")
        
        imported_objects = import_model(
            filepath=self.input_file,
            merge_vertices=merge_vertices,
            import_shading='NORMALS'
        )
        
        # Filter only mesh objects
        mesh_objects = [obj for obj in imported_objects if obj.type == 'MESH']
        
        logger.info(f"✓ Imported {len(mesh_objects)} mesh object(s)")
        
        return mesh_objects
    
    
    def get_material_clusters(
        self,
        meshes: Optional[List[bpy.types.Object]] = None,
        print_report: bool = True
    ) -> Dict[str, List[bpy.types.Object]]:
        """
        Get mesh clusters grouped by material.
        
        Args:
            meshes: List of meshes to cluster. If None, uses all meshes in scene.
            print_report: Print detailed cluster report
            
        Returns:
            Dictionary mapping material names to lists of mesh objects
        """
        logger.info("Clustering meshes by material...")
        
        # Get clusters
        clusters = MeshClusterManager.cluster_by_material(
            meshes=meshes,
            include_no_material=True
        )
        
        # Log summary
        stats = MeshClusterManager.get_cluster_statistics(clusters)
        logger.info(f"✓ Found {stats['total_materials']} material(s) across {stats['total_meshes']} mesh(es)")
        
        return clusters
    
    
    def run_basic_pipeline(self) -> Dict[str, List[bpy.types.Object]]:
        """
        Run the basic pipeline: cleanup, import, cluster.
        
        Returns:
            Dictionary of material clusters
        """
        
        # Step 1: Cleanup scene
        self.cleanup_scene()
        
        # Step 2: Import mesh
        imported_meshes = self.import_mesh(merge_vertices=True)
        
        # Step 3: Get material clusters
        clusters = self.get_material_clusters(
            meshes=imported_meshes,
            print_report=True
        )
        
        return clusters


# ==============================================================================
# Example Usage (for testing in Blender)
# ==============================================================================

if __name__ == "__main__":
    """
    Example usage when running this script directly in Blender.
    
    Usage in Blender:
        blender --background --python core.py
    """
    
    # Example: Analyze a model
    input_file = Path("/data/input/glb/rock.glb")
    
    if input_file.exists():
        
        # Create pipeline
        pipeline = MeshPipeline(input_file, verbose=True)
        
        # Run basic pipeline
        clusters = pipeline.run_basic_pipeline()

        print (clusters)
        
        # Preprocessa TUTTI i cluster
        processed_clusters = ClusterPreprocessor.preprocess_all_clusters(
            clusters=clusters,
            merge_distance=0.0001,  # Importante per merge bordi!
            triangulate=True
        )

        meshes_to_keep = list(processed_clusters.values())
        SceneManager.cleanup_keep_meshes(
            meshes_to_keep=meshes_to_keep,
            remove_orphan_data=True
        )

        bpy.ops.object.select_all(action='DESELECT')

        for cluster_name, cluster_object in processed_clusters.items():
            print (cluster_object.name, cluster_object.data.polygons)

            cluster_object.select_set(True)
            output_file = Path(f"/data/input/exported_clusters/{cluster_name}.glb")
            export_model(filepath=output_file)

            cluster_object.select_set(False)

    else:
        logger.error(f"Example file not found: {input_file}")
        logger.error("Update the input_file path in the __main__ section to test.")
