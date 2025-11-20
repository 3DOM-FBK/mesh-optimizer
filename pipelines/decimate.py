"""
3D Model Decimation Pipeline

This module provides an intelligent mesh decimation system that reduces polygon count
while maintaining geometric accuracy using Hausdorff distance measurements.
"""

import os
import sys
import random
from pathlib import Path
from typing import Tuple, Optional
import argparse

import bpy
import bmesh


# ============================================================================
# Configuration
# ============================================================================

class Config:
    """Configuration constants for the decimation pipeline."""
    
    # Quality presets: target polygon counts
    QUALITY_PRESETS = {
        'high': 200000,
        'medium': 50000,
        'low': 10000
    }
    
    # Decimation algorithm parameters
    MAX_DECIMATION_ATTEMPTS = 6
    HAUSDORFF_SCALING_FACTOR = 0.001
    TARGET_ADJUSTMENT_FACTOR = 1.5
    DEFAULT_SAMPLE_COUNT = 5000
    
    # Vertex merging threshold
    DEFAULT_MERGE_DISTANCE = 0.0001
    
    # Supported file formats
    SUPPORTED_FORMATS = {'.glb', '.gltf'}


# ============================================================================
# Argument Parsing
# ============================================================================

def parse_arguments() -> argparse.Namespace:
    """
    Parse command-line arguments for the decimation pipeline.
    
    Returns:
        argparse.Namespace: Parsed arguments containing input/output paths and quality.
    """
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = []

    parser = argparse.ArgumentParser(
        description="Decimate 3D models with quality control using Hausdorff distance."
    )
    parser.add_argument(
        '-i', '--input_file',
        type=str,
        required=True,
        help='Path to input 3D model file (.glb, .gltf)'
    )
    parser.add_argument(
        '-o', '--output_file',
        type=str,
        required=True,
        help='Path to output decimated model file'
    )
    parser.add_argument(
        '-q', '--quality',
        type=str,
        choices=['high', 'medium', 'low'],
        default='medium',
        help='Target quality level (default: medium)'
    )
    
    return parser.parse_args(argv)


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
            filepath: Path to the model file (.glb, .gltf).
        
        Returns:
            bpy.types.Object: The imported Blender object.
        
        Raises:
            FileNotFoundError: If the file doesn't exist.
            ValueError: If the file format is unsupported.
        """
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"File not found: {filepath}")
        
        ext = os.path.splitext(filepath)[1].lower()
        
        if ext not in Config.SUPPORTED_FORMATS:
            raise ValueError(
                f"Unsupported file format: {ext}. "
                f"Supported formats: {Config.SUPPORTED_FORMATS}"
            )
        
        bpy.ops.import_scene.gltf(
            filepath=filepath,
            merge_vertices=True
        )
        
        imported_objects = bpy.context.selected_objects
        if not imported_objects:
            raise RuntimeError("No objects were imported from the file.")
        
        return imported_objects[0]
    
    @staticmethod
    def export_model(obj: bpy.types.Object, filepath: str) -> None:
        """
        Export a Blender model to GLB format.
        
        Args:
            obj: The Blender object to export.
            filepath: Path where the file will be saved.
        
        Raises:
            TypeError: If the object is not a mesh.
            ValueError: If the file format is unsupported.
        """
        if obj.type != 'MESH':
            raise TypeError(f"Object '{obj.name}' is not a mesh.")
        
        ext = os.path.splitext(filepath)[1].lower()
        
        if ext not in Config.SUPPORTED_FORMATS:
            raise ValueError(
                f"Unsupported export format: {ext}. "
                f"Supported formats: {Config.SUPPORTED_FORMATS}"
            )
        
        # Select only the target object
        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        
        bpy.ops.export_scene.gltf(
            filepath=filepath,
            use_selection=True
        )


# ============================================================================
# Mesh Processing Operations
# ============================================================================

class MeshProcessor:
    """Handles mesh processing operations."""
    
    @staticmethod
    def merge_vertices(
        obj: bpy.types.Object,
        distance: float = Config.DEFAULT_MERGE_DISTANCE
    ) -> None:
        """
        Merge nearby vertices within a specified distance threshold.
        
        Args:
            obj: The Blender mesh object to process.
            distance: Maximum distance between vertices to merge.
        
        Raises:
            TypeError: If the object is not a mesh.
        """
        if obj.type != 'MESH':
            raise TypeError(f"Object '{obj.name}' is not a mesh.")
        
        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.remove_doubles(threshold=distance)
        bpy.ops.object.mode_set(mode='OBJECT')
    
    @staticmethod
    def apply_decimate_modifier(
        obj: bpy.types.Object,
        ratio: float,
        use_triangulate: bool = True
    ) -> None:
        """
        Apply a decimate modifier to reduce polygon count.
        
        Args:
            obj: The Blender mesh object to decimate.
            ratio: Target ratio of remaining geometry (0 < ratio <= 1.0).
            use_triangulate: Whether to triangulate collapsed geometry.
        
        Raises:
            TypeError: If the object is not a mesh.
            ValueError: If ratio is not in valid range.
        """
        if obj.type != 'MESH':
            raise TypeError(f"Object '{obj.name}' is not a mesh.")
        
        if not (0.0 < ratio <= 1.0):
            raise ValueError("Ratio must be between 0 (exclusive) and 1 (inclusive).")
        
        # Add and configure decimate modifier
        mod = obj.modifiers.new(name="Decimate", type='DECIMATE')
        mod.ratio = ratio
        mod.use_collapse_triangulate = use_triangulate
        
        # Apply the modifier
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.modifier_apply(modifier=mod.name)
    
    @staticmethod
    def duplicate_object(obj: bpy.types.Object, name_suffix: str = "_copy") -> bpy.types.Object:
        """
        Create a duplicate of a Blender object.
        
        Args:
            obj: The object to duplicate.
            name_suffix: Suffix to add to the duplicated object's name.
        
        Returns:
            bpy.types.Object: The duplicated object.
        """
        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        
        bpy.ops.object.duplicate()
        duplicated = bpy.context.active_object
        duplicated.name = f"{obj.name}{name_suffix}"
        
        return duplicated


# ============================================================================
# Geometric Distance Calculator
# ============================================================================

class HausdorffDistanceCalculator:
    """Calculates Hausdorff distance between two meshes using random sampling."""
    
    @staticmethod
    def compute_distance(
        obj_a: bpy.types.Object,
        obj_b: bpy.types.Object,
        sample_count: int = Config.DEFAULT_SAMPLE_COUNT
    ) -> float:
        """
        Approximate Hausdorff distance between two meshes via random sampling.
        
        The Hausdorff distance measures the maximum distance from any point
        on one mesh to the closest point on the other mesh.
        
        Args:
            obj_a: First mesh object.
            obj_b: Second mesh object.
            sample_count: Number of vertices to sample for approximation.
        
        Returns:
            float: Approximate Hausdorff distance.
        """
        depsgraph = bpy.context.evaluated_depsgraph_get()
        
        # Get evaluated meshes
        mesh_a = obj_a.evaluated_get(depsgraph).to_mesh()
        mesh_b = obj_b.evaluated_get(depsgraph).to_mesh()
        
        # Create BMesh structures
        bm_a = bmesh.new()
        bm_a.from_mesh(mesh_a)
        bm_a.verts.ensure_lookup_table()
        
        bm_b = bmesh.new()
        bm_b.from_mesh(mesh_b)
        bm_b.verts.ensure_lookup_table()
        
        try:
            # Sample random vertices
            total_verts_a = len(bm_a.verts)
            total_verts_b = len(bm_b.verts)
            
            sampled_a = random.sample(
                list(bm_a.verts),
                min(sample_count, total_verts_a)
            )
            sampled_b = random.sample(
                list(bm_b.verts),
                min(sample_count, total_verts_b)
            )
            
            max_distance = 0.0
            
            # Compute distance from A to B
            for vertex in sampled_a:
                _, closest_point, _, _ = obj_b.closest_point_on_mesh(vertex.co)
                distance = (vertex.co - closest_point).length
                max_distance = max(max_distance, distance)
            
            # Compute distance from B to A
            for vertex in sampled_b:
                _, closest_point, _, _ = obj_a.closest_point_on_mesh(vertex.co)
                distance = (vertex.co - closest_point).length
                max_distance = max(max_distance, distance)
            
            return max_distance
        
        finally:
            # Cleanup
            bm_a.free()
            bm_b.free()
            obj_a.to_mesh_clear()
            obj_b.to_mesh_clear()


# ============================================================================
# Intelligent Decimation Engine
# ============================================================================

class AdaptiveDecimator:
    """Performs adaptive mesh decimation with quality control."""
    
    def __init__(
        self,
        quality_preset: str,
        max_attempts: int = Config.MAX_DECIMATION_ATTEMPTS
    ):
        """
        Initialize the adaptive decimator.
        
        Args:
            quality_preset: Quality level ('high', 'medium', 'low').
            max_attempts: Maximum number of decimation attempts.
        """
        self.target_polygon_count = Config.QUALITY_PRESETS[quality_preset]
        self.max_attempts = max_attempts
        self.mesh_processor = MeshProcessor()
        self.distance_calculator = HausdorffDistanceCalculator()
    
    def decimate_with_quality_control(
        self,
        obj: bpy.types.Object,
        hausdorff_threshold: float
    ) -> bpy.types.Object:
        """
        Iteratively decimate mesh while maintaining quality via Hausdorff distance.
        
        This method progressively adjusts the target polygon count until
        the Hausdorff distance is within the acceptable threshold.
        
        Args:
            obj: The original mesh object to decimate.
            hausdorff_threshold: Maximum acceptable Hausdorff distance.
        
        Returns:
            bpy.types.Object: The decimated mesh object.
        
        Raises:
            ValueError: If the object is not a mesh.
        """
        if obj.type != 'MESH':
            raise ValueError("Object must be a mesh.")
        
        current_target = self.target_polygon_count
        decimated_obj = None
        
        print(f"Starting adaptive decimation with target: {current_target} polygons")
        print(f"Hausdorff threshold: {hausdorff_threshold:.6f}")
        
        for attempt in range(1, self.max_attempts + 1):
            print(f"\nAttempt {attempt}/{self.max_attempts}")
            
            # Remove previous attempt if exists
            if decimated_obj is not None:
                bpy.data.objects.remove(decimated_obj, do_unlink=True)
            
            # Create a fresh duplicate
            decimated_obj = self.mesh_processor.duplicate_object(
                obj,
                name_suffix="_decimated"
            )
            
            # Calculate and apply decimation ratio
            current_face_count = len(decimated_obj.data.polygons)
            ratio = min(current_target / current_face_count, 1.0)
            
            print(f"  Current faces: {current_face_count}")
            print(f"  Target faces: {current_target}")
            print(f"  Decimation ratio: {ratio:.4f}")
            
            self.mesh_processor.apply_decimate_modifier(
                decimated_obj,
                ratio=ratio,
                use_triangulate=True
            )
            
            final_face_count = len(decimated_obj.data.polygons)
            print(f"  Result faces: {final_face_count}")
            
            # Measure geometric accuracy
            hausdorff_distance = self.distance_calculator.compute_distance(
                obj,
                decimated_obj
            )
            
            print(f"  Hausdorff distance: {hausdorff_distance:.6f}")
            
            # Check if quality is acceptable
            if hausdorff_distance <= hausdorff_threshold:
                print(f"\n✓ Quality acceptable! Final face count: {final_face_count}")
                break
            else:
                print(f"  ✗ Quality insufficient, adjusting target...")
                current_target = int(
                    current_target * Config.TARGET_ADJUSTMENT_FACTOR
                )
        else:
            print(f"\n⚠ Reached maximum attempts. Using best result.")
        
        return decimated_obj


# ============================================================================
# Decimation Pipeline
# ============================================================================

class DecimationPipeline:
    """Orchestrates the complete decimation workflow."""
    
    def __init__(
        self,
        input_file: str,
        output_file: str,
        quality: str
    ):
        """
        Initialize the decimation pipeline.
        
        Args:
            input_file: Path to input 3D model.
            output_file: Path for output decimated model.
            quality: Quality preset ('high', 'medium', 'low').
        """
        self.input_file = Path(input_file)
        self.output_file = Path(output_file)
        self.quality = quality
        
        self.io_handler = ModelIOHandler()
        self.mesh_processor = MeshProcessor()
        self.decimator = AdaptiveDecimator(quality)
    
    def calculate_hausdorff_threshold(self, obj: bpy.types.Object) -> float:
        """
        Calculate an appropriate Hausdorff threshold based on model size.
        
        Args:
            obj: The mesh object to analyze.
        
        Returns:
            float: Calculated threshold value.
        """
        bbox_diagonal = obj.dimensions.length
        threshold = Config.HAUSDORFF_SCALING_FACTOR * bbox_diagonal
        return threshold
    
    def execute(self) -> str:
        """
        Execute the complete decimation pipeline.
        
        Returns:
            str: Path to the output file.
        """
        print(f"=" * 60)
        print(f"3D Model Decimation Pipeline")
        print(f"=" * 60)
        print(f"Input: {self.input_file}")
        print(f"Output: {self.output_file}")
        print(f"Quality: {self.quality}")
        print(f"=" * 60)
        
        # Import model
        print("\n[1/4] Importing model...")
        model = self.io_handler.import_model(str(self.input_file))
        original_face_count = len(model.data.polygons)
        print(f"  Original face count: {original_face_count}")
        
        # Merge duplicate vertices
        print("\n[2/4] Merging duplicate vertices...")
        self.mesh_processor.merge_vertices(model)
        
        # Calculate quality threshold
        print("\n[3/4] Calculating quality threshold...")
        hausdorff_threshold = self.calculate_hausdorff_threshold(model)
        
        # Perform adaptive decimation
        print("\n[4/4] Performing adaptive decimation...")
        decimated_model = self.decimator.decimate_with_quality_control(
            model,
            hausdorff_threshold
        )
        
        final_face_count = len(decimated_model.data.polygons)
        reduction_percentage = (1 - final_face_count / original_face_count) * 100
        
        # Export result
        print(f"\n[5/5] Exporting decimated model...")
        self.io_handler.export_model(decimated_model, str(self.output_file))
        
        # Summary
        print(f"\n" + "=" * 60)
        print(f"Decimation Complete!")
        print(f"=" * 60)
        print(f"Original faces: {original_face_count:,}")
        print(f"Final faces: {final_face_count:,}")
        print(f"Reduction: {reduction_percentage:.1f}%")
        print(f"Output saved to: {self.output_file}")
        print(f"=" * 60)
        
        return str(self.output_file)


# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    """Main entry point for the decimation pipeline."""
    try:
        args = parse_arguments()
        
        pipeline = DecimationPipeline(
            input_file=args.input_file,
            output_file=args.output_file,
            quality=args.quality
        )
        
        output_path = pipeline.execute()
        sys.exit(0)
    
    except Exception as e:
        print(f"\n✗ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()