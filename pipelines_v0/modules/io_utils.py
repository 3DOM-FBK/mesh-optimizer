"""
IO Utilities for 3D Model Import/Export using Blender
Simple functions for GLB/GLTF format operations
"""

import logging
from pathlib import Path
from typing import Union, List
import bpy
import sys
import os


logger = logging.getLogger(__name__)


def import_model(
    filepath: Union[str, Path],
    merge_vertices: bool = False,
    import_shading: str = 'NORMALS'
) -> List[bpy.types.Object]:
    """
    Import a 3D model from GLB/GLTF file into Blender.
    
    Args:
        filepath: Path to the GLB/GLTF file
        merge_vertices: Whether to merge vertices by distance
        import_shading: Shading mode ('NORMALS', 'FLAT', 'SMOOTH')
        
    Returns:
        List of imported Blender objects
        
    Raises:
        FileNotFoundError: If file doesn't exist
    """
    filepath = Path(filepath)
    
    if not filepath.exists():
        raise FileNotFoundError(f"File not found: {filepath}")
    
    logger.info(f"Importing model from: {filepath}")
    
    # Get objects before import
    objects_before = set(bpy.data.objects)
    
    # Import GLTF/GLB
    bpy.ops.import_scene.gltf(
        filepath=str(filepath),
        merge_vertices=merge_vertices,
        import_shading=import_shading
    )
    
    # Get newly imported objects
    objects_after = set(bpy.data.objects)
    imported_objects = list(objects_after - objects_before)
    
    logger.info(f"Successfully imported {len(imported_objects)} objects")
    
    return imported_objects


def export_model(
    filepath: Union[str, Path],
    export_format: str = 'GLB',
    selected_only: bool = False,
    export_materials: str = 'EXPORT',
    export_texcoords: bool = True,
    export_normals: bool = True,
    export_animations: bool = False,
    export_apply: bool = False
) -> bool:
    """
    Export Blender scene or selected objects to GLB/GLTF file.
    
    Args:
        filepath: Output file path
        export_format: 'GLB' (binary) or 'GLTF_SEPARATE' (text + bin + textures)
        selected_only: Export only selected objects
        export_materials: 'EXPORT', 'PLACEHOLDER', or 'NONE'
        export_texcoords: Whether to export texture coordinates
        export_normals: Whether to export normals
        export_animations: Whether to export animations
        export_apply: Whether to apply modifiers before export
        
    Returns:
        True if export successful
    """
    filepath = Path(filepath)
    
    logger.info(f"Exporting model to: {filepath}")
    
    # Create parent directory if needed
    filepath.parent.mkdir(parents=True, exist_ok=True)
    
    # Export GLTF/GLB
    bpy.ops.export_scene.gltf(
        filepath=str(filepath),
        export_format=export_format,
        use_selection=selected_only,
        export_materials=export_materials,
        export_texcoords=export_texcoords,
        export_normals=export_normals,
        export_animations=export_animations,
        export_apply=export_apply
    )
    
    # Verify export
    if not filepath.exists():
        logger.error(f"Export failed: file not created at {filepath}")
        return False
    
    file_size = filepath.stat().st_size
    logger.info(f"Successfully exported to {filepath} ({file_size / 1024:.2f} KB)")
    
    return True
