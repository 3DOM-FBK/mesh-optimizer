import os
import subprocess
import logging
import gmsh

# Logging configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# CGAL remesh binary path
CGAL_REMESH_BIN = "/opt/remesh"

class GmshConverter:
    """
    Class for mesh format conversion using Gmsh.
    """
    @staticmethod
    def obj_to_mesh(obj_path: str, output_path: str = None, generate_3d: bool = False) -> str:
        """
        Converts an OBJ file to MEDIT (.mesh) format.
        
        Args:
            obj_path (str): Input OBJ file path.
            output_path (str, optional): Output path. If None, uses same name with .mesh extension.
            generate_3d (bool): If True, attempts to generate a volumetric mesh (tetrahedral).
        """
        if not os.path.exists(obj_path):
            logger.error(f"Input file not found: {obj_path}")
            return None
            
        if output_path is None:
            output_path = os.path.splitext(obj_path)[0] + ".mesh"
            
        try:
            if not gmsh.isInitialized():
                gmsh.initialize()
            
            gmsh.clear()
            # Merge loads the file into current Gmsh scene
            gmsh.merge(obj_path)
            
            if generate_3d:
                logger.info("Attempting volumetric mesh generation (3D)...")
                gmsh.model.mesh.generate(3)
            
            gmsh.write(output_path)
            logger.info(f"OBJ -> MESH conversion completed: {output_path}")
            
            return output_path
        except Exception as e:
            logger.error(f"Error converting OBJ -> MESH: {e}")
            return None

    @staticmethod
    def mesh_to_obj(mesh_path: str, output_path: str = None) -> str:
        """
        Converts a .mesh file to OBJ.
        """
        if not os.path.exists(mesh_path):
            logger.error(f"Input file not found: {mesh_path}")
            return None

        if output_path is None:
            output_path = os.path.splitext(mesh_path)[0] + ".obj"

        try:
            if not gmsh.isInitialized():
                gmsh.initialize()
            
            gmsh.clear()
            gmsh.merge(mesh_path)
            gmsh.write(output_path)
            logger.info(f"MESH -> OBJ conversion completed: {output_path}")
            return output_path
        except Exception as e:
             logger.error(f"Error converting MESH -> OBJ: {e}")
             return None


class CgalRemesher:
    """
    Wrapper class for executing CGAL Adaptive Isotropic Remeshing tool.
    
    Uses compiled binary from CGAL 6.1 supporting:
    - Adaptive sizing field based on local curvature
    - Automatic edge preservation (open meshes)
    - Supported formats: OBJ, OFF, PLY
    """
    
    @staticmethod
    def remesh(
        input_path: str,
        output_path: str = None,
        tolerance: float = 0.001,
        edge_min: float = None,
        edge_max: float = None,
        iterations: int = 5,
        cgal_bin: str = CGAL_REMESH_BIN
    ) -> str:
        """
        Executes adaptive remeshing using CGAL.
        
        Args:
            input_path (str): Input mesh file path (OBJ, OFF, PLY).
            output_path (str, optional): Output file path. Default: *_remeshed.obj
            tolerance (float): Approximation tolerance for curvature adaptation.
                               Lower values = shorter edges in curved areas.
                               Default: 0.001
            edge_min (float, optional): Minimum edge length. 
                                        Default: auto (0.1% of bbox diagonal).
            edge_max (float, optional): Maximum edge length.
                                        Default: auto (5% of bbox diagonal).
            iterations (int): Number of remeshing iterations. Default: 5
            cgal_bin (str): CGAL remesh binary path. Default: /opt/remesh
            
        Returns:
            str: Output file path if successful, None otherwise.
        """
        if not os.path.exists(input_path):
            logger.error(f"Input file not found: {input_path}")
            return None
        
        if not os.path.exists(cgal_bin):
            logger.error(f"CGAL binary not found: {cgal_bin}")
            return None
            
        if output_path is None:
            base, ext = os.path.splitext(input_path)
            output_path = f"{base}_remeshed{ext}"
        
        # Build command
        cmd = [cgal_bin, input_path, output_path, str(tolerance)]
        
        # Add edge_min and edge_max if specified
        if edge_min is not None:
            cmd.append(str(edge_min))
            if edge_max is not None:
                cmd.append(str(edge_max))
                cmd.append(str(iterations))
        elif iterations != 5:
            # If we only want to change iterations, we must pass all parameters
            # In this case we leave defaults for edge_min/max
            pass
        
        logger.info(f"Executing CGAL remesh: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                logger.error(f"CGAL remesh Error (Code {result.returncode}): {result.stderr}")
                logger.error(f"CGAL Output: {result.stdout}")
                return None
            
            # Log tool output
            if result.stdout:
                for line in result.stdout.strip().split('\n'):
                    logger.info(f"[CGAL] {line}")
            
            if os.path.exists(output_path):
                logger.info(f"CGAL Remeshing completed: {output_path}")
                return output_path
            else:
                logger.error(f"Output file not created: {output_path}")
                return None
                
        except Exception as e:
            logger.error(f"Exception during CGAL remesh execution: {e}")
            return None
    
    @staticmethod
    def adaptive_remesh(
        input_path: str,
        output_path: str = None,
        detail_level: str = "high",
        iterations: int = 5,
        cgal_bin: str = CGAL_REMESH_BIN
    ) -> str:
        """
        Adaptive remeshing with predefined detail presets.
        
        Args:
            input_path (str): Input mesh file path.
            output_path (str, optional): Output file path.
            detail_level (str): Detail level:
                - "low": high tolerance, fewer triangles
                - "medium": balanced
                - "high": low tolerance, more detail on curves (default)
                - "ultra": max detail
            iterations (int): Number of iterations. Default: 5
            cgal_bin (str): CGAL binary path.
            
        Returns:
            str: Output file path if successful, None otherwise.
        """
        # Tolerance presets for each level
        tolerance_presets = {
            "low": 0.01,
            "medium": 0.001,
            "high": 0.0005,
            "ultra": 0.0001
        }
        
        tolerance = tolerance_presets.get(detail_level, 0.001)
        
        logger.info(f"Adaptive remeshing with level '{detail_level}' (tolerance={tolerance})")
        
        return CgalRemesher.remesh(
            input_path=input_path,
            output_path=output_path,
            tolerance=tolerance,
            iterations=iterations,
            cgal_bin=cgal_bin
        )
