"""
3D Model Remeshing Pipeline

This module provides a complete pipeline for remeshing 3D models using MMG and Gmsh.
It handles model import/export via Blender and orchestrates the remeshing workflow.
"""

import os
import sys
import subprocess
import glob
from pathlib import Path
from typing import Optional, Tuple, List
import argparse

import gmsh
import bpy


# ============================================================================
# Configuration
# ============================================================================

class Config:
    """Configuration constants for the remeshing pipeline."""
    MMG_EXECUTABLE_PATH = '/opt/mmg/build/bin/mmgs_O3'
    SUPPORTED_IMPORT_FORMATS = {'.obj', '.glb', '.gltf'}
    SUPPORTED_EXPORT_FORMATS = {'.glb', '.obj'}
    TEMP_FILE_PATTERNS = ['*.obj', '*.mesh']


# ============================================================================
# Argument Parsing
# ============================================================================

def parse_arguments() -> argparse.Namespace:
    """
    Parse command-line arguments for the remeshing pipeline.
    
    Returns:
        argparse.Namespace: Parsed arguments containing dir_path.
    """
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = []

    parser = argparse.ArgumentParser(
        description="Process and remesh 3D models using MMG and Blender."
    )
    parser.add_argument(
        '-i', '--dir_path',
        type=str,
        required=True,
        help='Input directory path containing the 3D model'
    )
    
    return parser.parse_args(argv)


# ============================================================================
# MMG Executable Runner
# ============================================================================

class MMGRunner:
    """Handles execution of the MMG remeshing executable."""
    
    def __init__(self, executable_path: str = Config.MMG_EXECUTABLE_PATH):
        """
        Initialize the MMG runner.
        
        Args:
            executable_path: Path to the MMG executable.
        """
        self.executable_path = os.path.abspath(executable_path)
    
    def run(self, args: Optional[List[str]] = None, verbose: bool = False) -> bool:
        """
        Execute the MMG remeshing tool.
        
        Args:
            args: List of command-line arguments for MMG.
            verbose: If True, display stdout/stderr from the process.
        
        Returns:
            bool: True if execution succeeded, False otherwise.
        """
        cmd = [self.executable_path]
        
        if args:
            cmd.extend(args)
        
        try:
            if verbose:
                result = subprocess.run(cmd, check=True)
            else:
                result = subprocess.run(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL,
                    check=True
                )
            return result.returncode == 0
        except (subprocess.CalledProcessError, FileNotFoundError, Exception):
            return False


# ============================================================================
# Blender Model Handler
# ============================================================================

class BlenderModelHandler:
    """Handles 3D model import and export operations in Blender."""
    
    @staticmethod
    def import_model(filepath: str) -> bpy.types.Object:
        """
        Import a 3D model into Blender.
        
        Args:
            filepath: Path to the model file (.obj, .glb, .gltf).
        
        Returns:
            bpy.types.Object: The imported Blender object.
        
        Raises:
            FileNotFoundError: If the file doesn't exist.
            ValueError: If the file format is unsupported.
        """
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"File not found: {filepath}")
        
        ext = os.path.splitext(filepath)[1].lower()
        
        if ext not in Config.SUPPORTED_IMPORT_FORMATS:
            raise ValueError(
                f"Unsupported file format: {ext}. "
                f"Supported formats: {Config.SUPPORTED_IMPORT_FORMATS}"
            )
        
        bpy.ops.object.select_all(action='DESELECT')
        
        if ext == ".obj":
            bpy.ops.wm.obj_import(filepath=filepath)
        elif ext in (".glb", ".gltf"):
            bpy.ops.import_scene.gltf(
                filepath=filepath,
                merge_vertices=True
            )
        
        return bpy.context.selected_objects[0]
    
    @staticmethod
    def export_model(
        model: bpy.types.Object,
        dir_path: str,
        ext: str = ".glb",
        use_selection: bool = True
    ) -> str:
        """
        Export a Blender model to file.
        
        Args:
            model: The Blender object to export.
            dir_path: Directory where the file will be saved.
            ext: File extension (.glb or .obj).
            use_selection: If True, export only selected objects.
        
        Returns:
            str: Path to the exported file.
        
        Raises:
            TypeError: If the object is not a mesh.
            ValueError: If the export format is unsupported.
        """
        if model.type != 'MESH':
            raise TypeError(f"Object '{model.name}' is not a mesh.")
        
        if ext not in Config.SUPPORTED_EXPORT_FORMATS:
            raise ValueError(
                f"Unsupported export format: {ext}. "
                f"Supported formats: {Config.SUPPORTED_EXPORT_FORMATS}"
            )
        
        # Select only the target model
        bpy.ops.object.select_all(action='DESELECT')
        model.select_set(True)
        bpy.context.view_layer.objects.active = model
        
        filepath = os.path.join(dir_path, f"remesh{ext}")
        
        if ext == ".glb":
            bpy.ops.export_scene.gltf(
                filepath=filepath,
                export_format='GLB',
                use_selection=use_selection
            )
        elif ext == ".obj":
            bpy.ops.wm.obj_export(
                filepath=filepath,
                export_materials=False
            )
        
        return filepath


# ============================================================================
# Gmsh Mesh Processor
# ============================================================================

class GmshProcessor:
    """Handles mesh conversion operations using Gmsh."""
    
    @staticmethod
    def prepare_for_mmg(file_path: str) -> Tuple[str, str]:
        """
        Convert a 3D model to .mesh format for MMG processing.
        
        Args:
            file_path: Path to the input 3D model file.
        
        Returns:
            Tuple[str, str]: Paths to (input .mesh file, expected output .mesh file).
        """
        gmsh.initialize()
        
        try:
            # Import and generate mesh
            gmsh.merge(file_path)
            gmsh.model.mesh.generate(3)
            
            # Determine output paths
            folder = os.path.dirname(file_path)
            base_name = os.path.splitext(os.path.basename(file_path))[0]
            
            mesh_path = os.path.join(folder, f"{base_name}.mesh")
            output_path = os.path.join(folder, f"{base_name}_res.mesh")
            
            # Write the mesh file
            gmsh.write(mesh_path)
            
            return mesh_path, output_path
        finally:
            gmsh.finalize()
    
    @staticmethod
    def convert_to_obj(mesh_path: str) -> str:
        """
        Convert a .mesh file to Wavefront OBJ format.
        
        Args:
            mesh_path: Path to the input .mesh file.
        
        Returns:
            str: Path to the generated .obj file.
        """
        gmsh.initialize()
        
        try:
            # Load the mesh file
            gmsh.merge(mesh_path)
            
            # Determine output path
            folder = os.path.dirname(mesh_path)
            base_name = os.path.splitext(os.path.basename(mesh_path))[0]
            obj_path = os.path.join(folder, f"{base_name}.obj")
            
            # Write OBJ file
            gmsh.write(obj_path)
            
            return obj_path
        finally:
            gmsh.finalize()


# ============================================================================
# Remeshing Pipeline
# ============================================================================

class RemeshingPipeline:
    """Orchestrates the complete remeshing workflow."""
    
    def __init__(self, dir_path: str):
        """
        Initialize the remeshing pipeline.
        
        Args:
            dir_path: Working directory for the pipeline.
        """
        self.dir_path = Path(dir_path)
        self.mmg_runner = MMGRunner()
        self.blender_handler = BlenderModelHandler()
        self.gmsh_processor = GmshProcessor()
    
    def remesh_geometry(self, file_path: str) -> Tuple[bool, str]:
        """
        Perform complete remeshing operation on a geometry file.
        
        Args:
            file_path: Path to the input geometry file.
        
        Returns:
            Tuple[bool, str]: (Success status, path to remeshed OBJ file).
        """
        # Prepare mesh for MMG
        mesh_input, mesh_output = self.gmsh_processor.prepare_for_mmg(file_path)
        
        # Run MMG remeshing
        args = ["-in", mesh_input, "-out", mesh_output]
        success = self.mmg_runner.run(args)
        
        if not success:
            return False, ""
        
        # Convert result back to OBJ
        obj_path = self.gmsh_processor.convert_to_obj(mesh_output)
        
        return True, obj_path
    
    def cleanup_temp_files(self):
        """Remove all temporary mesh files from the working directory."""
        for pattern in Config.TEMP_FILE_PATTERNS:
            files = glob.glob(
                str(self.dir_path / "**" / pattern),
                recursive=True
            )
            for file_path in files:
                try:
                    os.remove(file_path)
                except Exception:
                    pass  # Silently ignore cleanup errors
    
    def execute(self) -> bool:
        """
        Execute the complete remeshing pipeline.
        
        Returns:
            bool: True if pipeline completed successfully, False otherwise.
        """
        temp_obj = self.dir_path / "remesh.obj"
        temp_glb = self.dir_path / "temp_model.glb"
        
        # Initialize clean Blender scene
        bpy.ops.wm.read_factory_settings(use_empty=True)
        
        # Import original model
        print(f"Importing model: {temp_glb}")
        model = self.blender_handler.import_model(str(temp_glb))
        
        # Export as OBJ for remeshing
        print(f"Exporting to OBJ: {temp_obj}")
        self.blender_handler.export_model(
            model,
            str(self.dir_path),
            ext=".obj",
            use_selection=True
        )
        
        # Perform remeshing
        print("Running remeshing operation...")
        success, remeshed_obj = self.remesh_geometry(str(temp_obj))
        
        if not success:
            print("Remeshing failed!")
            return False
        
        # Reset scene and import remeshed model
        bpy.ops.wm.read_factory_settings(use_empty=True)
        print(f"Importing remeshed model: {remeshed_obj}")
        remeshed_model = self.blender_handler.import_model(remeshed_obj)
        
        # Export final GLB
        print("Exporting final GLB...")
        self.blender_handler.export_model(
            remeshed_model,
            str(self.dir_path),
            ext=".glb",
            use_selection=True
        )
        
        # Cleanup temporary files
        print("Cleaning up temporary files...")
        self.cleanup_temp_files()
        
        print("Pipeline completed successfully!")
        return True


# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    """Main entry point for the remeshing pipeline."""
    args = parse_arguments()
    
    pipeline = RemeshingPipeline(args.dir_path)
    success = pipeline.execute()
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()