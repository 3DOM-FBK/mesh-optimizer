"""
3D Model Preprocessing Pipeline

This module provides a complete pipeline for preprocessing 3D models in Blender.
It handles model import, geometry cleanup, mesh optimization, and export operations.
"""

import os
import sys
from pathlib import Path
from typing import Optional, List
import argparse

import bpy
import bmesh


# ============================================================================
# Configuration
# ============================================================================

class Config:
    """Configuration constants for the preprocessing pipeline."""
    SUPPORTED_IMPORT_FORMATS = {'.obj', '.glb', '.gltf'}
    SUPPORTED_EXPORT_FORMATS = {'.glb'}
    DEFAULT_MERGE_THRESHOLD = 0.001
    TEMP_DIR_BASE = "/tmp"


# ============================================================================
# Argument Parsing
# ============================================================================

def parse_arguments() -> argparse.Namespace:
    """
    Parse command-line arguments for the preprocessing pipeline.
    
    Returns:
        argparse.Namespace: Parsed arguments containing input_file path.
    """
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = []

    parser = argparse.ArgumentParser(
        description="Preprocess 3D models: clean geometry, triangulate, and export."
    )
    parser.add_argument(
        '-i', '--input_file',
        type=str,
        required=True,
        help='Path to input 3D model file (.obj, .glb, .gltf)'
    )
    
    return parser.parse_args(argv)


# ============================================================================
# Scene Management
# ============================================================================

class SceneManager:
    """Handles Blender scene operations."""
    
    @staticmethod
    def clear_scene() -> None:
        """Remove all objects from the current Blender scene."""
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete(use_global=False)
    
    @staticmethod
    def ensure_object_mode() -> None:
        """Ensure Blender is in Object mode."""
        if bpy.context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
    
    @staticmethod
    def set_active_object(obj: bpy.types.Object) -> None:
        """
        Set an object as the active object in the scene.
        
        Args:
            obj: The Blender object to make active.
        """
        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj


# ============================================================================
# Model Import/Export Handler
# ============================================================================

class ModelIOHandler:
    """Handles 3D model import and export operations."""
    
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
            bpy.ops.import_scene.gltf(filepath=filepath)
        
        imported_objects = bpy.context.selected_objects
        if not imported_objects:
            raise RuntimeError("No objects were imported from the file.")
        
        return imported_objects[0]
    
    @staticmethod
    def export_glb(
        model: bpy.types.Object,
        output_dir: str,
        filename: str = "temp_model.glb",
        use_selection: bool = True
    ) -> str:
        """
        Export a Blender model to GLB format.
        
        Args:
            model: The Blender object to export.
            output_dir: Directory where the file will be saved.
            filename: Name of the output file.
            use_selection: If True, export only selected objects.
        
        Returns:
            str: Path to the exported file.
        
        Raises:
            TypeError: If the object is not a mesh.
        """
        if model.type != 'MESH':
            raise TypeError(f"Object '{model.name}' is not a mesh.")
        
        # Select only the target model
        bpy.ops.object.select_all(action='DESELECT')
        model.select_set(True)
        bpy.context.view_layer.objects.active = model
        
        filepath = os.path.join(output_dir, filename)
        
        bpy.ops.export_scene.gltf(
            filepath=filepath,
            export_format='GLB',
            use_selection=use_selection
        )
        
        return filepath


# ============================================================================
# Mesh Geometry Operations
# ============================================================================

class MeshGeometryProcessor:
    """Handles geometric operations on mesh objects."""
    
    @staticmethod
    def remove_loose_geometry(obj: bpy.types.Object) -> None:
        """
        Remove all loose geometry from a mesh object.
        
        This removes vertices not connected to any edges and edges
        not connected to any faces.
        
        Args:
            obj: The Blender mesh object to clean.
        
        Raises:
            TypeError: If the object is not a mesh.
        """
        if obj.type != 'MESH':
            raise TypeError(f"Object '{obj.name}' is not a mesh.")
        
        SceneManager.ensure_object_mode()
        SceneManager.set_active_object(obj)
        
        # Use BMesh for precise geometry manipulation
        mesh = obj.data
        bm = bmesh.new()
        bm.from_mesh(mesh)
        
        # Select loose vertices (not connected to any edge)
        loose_verts = [v for v in bm.verts if len(v.link_edges) == 0]
        for v in loose_verts:
            v.select = True
        
        # Select loose edges (not connected to any face)
        loose_edges = [e for e in bm.edges if len(e.link_faces) == 0]
        for e in loose_edges:
            e.select = True
        
        # Apply changes and delete selected geometry
        bm.to_mesh(mesh)
        bm.free()
        
        if loose_verts or loose_edges:
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.delete(type='VERT')
            bpy.ops.object.mode_set(mode='OBJECT')
    
    @staticmethod
    def triangulate_mesh(obj: bpy.types.Object) -> None:
        """
        Triangulate all faces of a mesh object.
        
        Args:
            obj: The Blender mesh object to triangulate.
        
        Raises:
            TypeError: If the object is not a mesh.
        """
        if obj.type != 'MESH':
            raise TypeError(f"Object '{obj.name}' is not a mesh.")
        
        SceneManager.ensure_object_mode()
        SceneManager.set_active_object(obj)
        
        mesh = obj.data
        bm = bmesh.new()
        bm.from_mesh(mesh)
        
        bmesh.ops.triangulate(bm, faces=bm.faces[:])
        
        bm.to_mesh(mesh)
        bm.free()
        mesh.update()
    
    @staticmethod
    def fix_non_manifold_geometry(
        obj: bpy.types.Object,
        merge_distance: float = Config.DEFAULT_MERGE_THRESHOLD
    ) -> None:
        """
        Select and fix non-manifold geometry by merging vertices.
        
        Args:
            obj: The Blender mesh object to fix.
            merge_distance: Distance threshold for merging vertices.
        
        Raises:
            TypeError: If the object is not a mesh.
        """
        if obj.type != 'MESH':
            raise TypeError(f"Object '{obj.name}' is not a mesh.")
        
        SceneManager.ensure_object_mode()
        SceneManager.set_active_object(obj)
        
        # Enter Edit mode and select non-manifold geometry
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_mode(
            use_extend=False,
            use_expand=False,
            type='VERT'
        )
        
        bpy.ops.mesh.select_all(action='DESELECT')
        bpy.ops.mesh.select_non_manifold()
        
        # Merge vertices by distance
        bpy.ops.mesh.remove_doubles(threshold=merge_distance)
        
        bpy.ops.object.mode_set(mode='OBJECT')


# ============================================================================
# Mesh Hierarchy Operations
# ============================================================================

class MeshHierarchyProcessor:
    """Handles operations on mesh hierarchies and collections."""
    
    @staticmethod
    def flatten_and_join_hierarchy(
        root_name: str,
        merge_vertices_threshold: Optional[float] = None
    ) -> bpy.types.Object:
        """
        Flatten a mesh hierarchy and join all meshes into one.
        
        This function removes parent relationships, applies transforms,
        and combines all child meshes into a single object.
        
        Args:
            root_name: Name of the root object.
            merge_vertices_threshold: If provided, merge vertices closer than this distance.
        
        Returns:
            bpy.types.Object: The combined mesh object.
        
        Raises:
            ValueError: If the root object is not found or has no mesh children.
        """
        root = bpy.data.objects.get(root_name)
        if root is None:
            raise ValueError(f"Root object '{root_name}' not found")
        
        # Find all mesh children
        meshes = [
            obj for obj in root.children_recursive
            if obj.type == 'MESH'
        ]
        
        if not meshes:
            raise ValueError(f"No mesh objects found under '{root_name}'")
        
        # Apply parent transforms and unparent
        for mesh in meshes:
            mesh.matrix_world = root.matrix_world @ mesh.matrix_local
            mesh.parent = None
            mesh.matrix_parent_inverse.identity()
        
        # Join all meshes
        bpy.ops.object.select_all(action='DESELECT')
        for mesh in meshes:
            mesh.select_set(True)
        
        bpy.context.view_layer.objects.active = meshes[0]
        bpy.ops.object.join()
        
        combined_mesh = bpy.context.view_layer.objects.active
        combined_mesh.matrix_world = root.matrix_world
        
        # Optionally merge vertices
        if merge_vertices_threshold is not None:
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.select_all(action='SELECT')
            bpy.ops.mesh.remove_doubles(threshold=merge_vertices_threshold)
            bpy.ops.object.mode_set(mode='OBJECT')
            combined_mesh.data.update()
        
        return combined_mesh
    
    @staticmethod
    def join_all_scene_meshes() -> bpy.types.Object:
        """
        Join all mesh objects in the current scene into one.
        
        Returns:
            bpy.types.Object: The combined mesh object.
        
        Raises:
            ValueError: If no mesh objects are found in the scene.
        """
        bpy.ops.object.select_all(action='DESELECT')
        
        mesh_objects = [
            obj for obj in bpy.context.scene.objects
            if obj.type == 'MESH'
        ]
        
        if not mesh_objects:
            raise ValueError("No mesh objects found in the scene.")
        
        for obj in mesh_objects:
            obj.select_set(True)
        
        bpy.context.view_layer.objects.active = mesh_objects[0]
        bpy.ops.object.join()
        
        return bpy.context.view_layer.objects.active


# ============================================================================
# Preprocessing Pipeline
# ============================================================================

class PreprocessingPipeline:
    """Orchestrates the complete model preprocessing workflow."""
    
    def __init__(self, input_file: str):
        """
        Initialize the preprocessing pipeline.
        
        Args:
            input_file: Path to the input 3D model file.
        """
        self.input_file = Path(input_file)
        self.scene_manager = SceneManager()
        self.io_handler = ModelIOHandler()
        self.geometry_processor = MeshGeometryProcessor()
        self.hierarchy_processor = MeshHierarchyProcessor()
        
        # Determine output directory
        dataset_name = self.input_file.stem
        self.output_dir = Path(Config.TEMP_DIR_BASE) / dataset_name
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def process_imported_model(
        self,
        model: bpy.types.Object,
        file_extension: str
    ) -> bpy.types.Object:
        """
        Process the imported model based on its file type.
        
        Args:
            model: The imported Blender object.
            file_extension: The file extension of the imported model.
        
        Returns:
            bpy.types.Object: The processed mesh object.
        """
        if file_extension == ".glb":
            print("Processing GLB: flattening and joining hierarchy...")
            return self.hierarchy_processor.flatten_and_join_hierarchy(
                model.name
            )
        elif file_extension == ".obj":
            print("Processing OBJ: joining all meshes...")
            return self.hierarchy_processor.join_all_scene_meshes()
        else:
            return model
    
    def clean_geometry(self, model: bpy.types.Object) -> None:
        """
        Apply all geometry cleaning operations.
        
        Args:
            model: The mesh object to clean.
        """
        print("Fixing non-manifold geometry...")
        self.geometry_processor.fix_non_manifold_geometry(model)
        
        print("Removing loose geometry...")
        self.geometry_processor.remove_loose_geometry(model)
        
        print("Triangulating mesh...")
        self.geometry_processor.triangulate_mesh(model)
    
    def execute(self) -> str:
        """
        Execute the complete preprocessing pipeline.
        
        Returns:
            str: Path to the exported GLB file.
        """
        print(f"Starting preprocessing pipeline for: {self.input_file}")
        
        # Clear scene
        print("Clearing scene...")
        self.scene_manager.clear_scene()
        
        # Import model
        print(f"Importing model: {self.input_file}")
        model = self.io_handler.import_model(str(self.input_file))
        
        # Process based on file type
        file_extension = self.input_file.suffix.lower()
        model = self.process_imported_model(model, file_extension)
        
        # Clean and optimize geometry
        self.clean_geometry(model)
        
        # Export final model
        print(f"Exporting to: {self.output_dir}")
        output_path = self.io_handler.export_glb(
            model,
            str(self.output_dir),
            filename="temp_model.glb",
            use_selection=True
        )
        
        print(f"Pipeline completed successfully!")
        print(f"Output file: {output_path}")
        
        return output_path


# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    """Main entry point for the preprocessing pipeline."""
    try:
        args = parse_arguments()
        
        pipeline = PreprocessingPipeline(args.input_file)
        output_path = pipeline.execute()
        
        sys.exit(0)
    
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()