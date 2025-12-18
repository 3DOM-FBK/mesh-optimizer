"""
Cluster Preprocessing Module

This module provides preprocessing operations for mesh clusters:
- Join meshes within a cluster
- Clean geometry and merge boundary vertices
- Fix non-manifold geometry
"""

import bpy
import bmesh
import logging
from typing import List, Dict, Optional
import sys
import os


logger = logging.getLogger(__name__)


class ClusterPreprocessor:
    """
    Preprocessor for mesh clusters.
    
    This class provides functionality to:
    - Join all meshes in a cluster into a single mesh
    - Clean geometry (remove loose vertices, fix non-manifold)
    - Merge boundary vertices between original mesh parts
    - Triangulate mesh
    """
    
    DEFAULT_MERGE_DISTANCE = 0.0001
    
    
    @staticmethod
    def join_cluster_meshes(
        mesh_list: List[bpy.types.Object],
        cluster_name: str = "JoinedCluster",
        merge_distance: float = DEFAULT_MERGE_DISTANCE
    ) -> bpy.types.Object:
        """
        Join all meshes in a cluster into a single mesh.
        
        IMPORTANT: After joining, this function automatically merges duplicate vertices
        at the boundaries between meshes to prevent non-manifold geometry.
        
        Args:
            mesh_list: List of mesh objects to join
            cluster_name: Name for the joined mesh
            merge_distance: Distance threshold for merging boundary vertices (default: 0.0001)
            
        Returns:
            The joined mesh object
            
        Raises:
            ValueError: If mesh_list is empty or contains non-mesh objects
            
        Example:
            >>> meshes = [mesh1, mesh2, mesh3]
            >>> joined = ClusterPreprocessor.join_cluster_meshes(meshes, "Material_001_Cluster")
        """
        if not mesh_list:
            raise ValueError("mesh_list cannot be empty")
        
        # Validate all objects are meshes
        for obj in mesh_list:
            if obj.type != 'MESH':
                raise ValueError(f"Object '{obj.name}' is not a mesh (type: {obj.type})")
        
        logger.info(f"Joining {len(mesh_list)} meshes into cluster '{cluster_name}'...")
        
        # If only one mesh, just rename and return
        if len(mesh_list) == 1:
            mesh_list[0].name = cluster_name
            logger.info(f"  Only 1 mesh, renamed to: {cluster_name}")
            return mesh_list[0]
        
        # Ensure in Object mode
        if bpy.context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        
        # Deselect all
        bpy.ops.object.select_all(action='DESELECT')
        
        # Select all meshes in the cluster
        for mesh_obj in mesh_list:
            mesh_obj.select_set(True)
        
        # Set first mesh as active
        bpy.context.view_layer.objects.active = mesh_list[0]
        
        # Store vertex count before join
        total_verts_before = sum(len(m.data.vertices) for m in mesh_list)
        
        # Join meshes
        bpy.ops.object.join()
        
        # Get joined object
        joined_mesh = bpy.context.view_layer.objects.active
        joined_mesh.name = cluster_name
        
        logger.info(f"  ✓ Joined {len(mesh_list)} meshes")
        logger.info(f"    Vertices before join: {total_verts_before}")
        
        # CRITICAL: Merge duplicate vertices at boundaries
        logger.info(f"  Merging boundary vertices (threshold: {merge_distance})...")
        
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        
        # Remove doubles (merge by distance)
        result = bpy.ops.mesh.remove_doubles(threshold=merge_distance)
        
        bpy.ops.object.mode_set(mode='OBJECT')
        
        # Update mesh
        joined_mesh.data.update()
        
        verts_after = len(joined_mesh.data.vertices)
        verts_merged = total_verts_before - verts_after
        
        logger.info(f"  ✓ Merged {verts_merged} duplicate vertices")
        logger.info(f"    Final vertices: {verts_after}")
        logger.info(f"    Final faces: {len(joined_mesh.data.polygons)}")
        
        return joined_mesh
    
    
    @staticmethod
    def clean_geometry(
        obj: bpy.types.Object,
        remove_loose: bool = True,
        fix_non_manifold: bool = False,
        merge_distance: float = DEFAULT_MERGE_DISTANCE
    ) -> None:
        """
        Clean mesh geometry by removing loose elements and fixing non-manifold geometry.
        
        Args:
            obj: Mesh object to clean
            remove_loose: Remove loose vertices and edges
            fix_non_manifold: Fix non-manifold geometry by merging vertices
            merge_distance: Distance threshold for merging vertices
            
        Raises:
            TypeError: If object is not a mesh
            
        Example:
            >>> ClusterPreprocessor.clean_geometry(mesh_obj)
        """
        if obj.type != 'MESH':
            raise TypeError(f"Object '{obj.name}' is not a mesh")
        
        logger.info(f"Cleaning geometry for: {obj.name}")
        
        # Ensure Object mode
        if bpy.context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        
        # Set as active
        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        
        # Remove loose geometry
        if remove_loose:
            logger.info("  Removing loose geometry...")
            ClusterPreprocessor._remove_loose_geometry(obj)
        
        # Fix non-manifold geometry
        if fix_non_manifold:
            logger.info("  Fixing non-manifold geometry...")
            ClusterPreprocessor._fix_non_manifold(obj, merge_distance)
        
        logger.info(f"  ✓ Geometry cleaned")
    
    
    @staticmethod
    def _remove_loose_geometry(obj: bpy.types.Object) -> None:
        """
        Remove loose vertices and edges (internal method).
        
        Args:
            obj: Mesh object
        """
        mesh = obj.data
        bm = bmesh.new()
        bm.from_mesh(mesh)
        
        # Find loose vertices and edges
        loose_verts = [v for v in bm.verts if len(v.link_edges) == 0]
        loose_edges = [e for e in bm.edges if len(e.link_faces) == 0]
        
        # Select them
        for v in loose_verts:
            v.select = True
        for e in loose_edges:
            e.select = True
        
        bm.to_mesh(mesh)
        bm.free()
        
        # Delete if found
        if loose_verts or loose_edges:
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.delete(type='VERT')
            bpy.ops.object.mode_set(mode='OBJECT')
            logger.info(f"    Removed {len(loose_verts)} loose vertices, {len(loose_edges)} loose edges")
    
    
    @staticmethod
    def _fix_non_manifold(obj: bpy.types.Object, merge_distance: float) -> None:
        """
        Fix non-manifold geometry by merging vertices (internal method).
        
        Args:
            obj: Mesh object
            merge_distance: Merge distance threshold
        """
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_mode(use_extend=False, use_expand=False, type='VERT')
        bpy.ops.mesh.select_all(action='DESELECT')
        bpy.ops.mesh.select_non_manifold()
        
        # Merge vertices by distance
        bpy.ops.mesh.remove_doubles(threshold=merge_distance)
        bpy.ops.object.mode_set(mode='OBJECT')
        
        logger.info(f"    Fixed non-manifold geometry")
    
    
    @staticmethod
    def triangulate_mesh(obj: bpy.types.Object) -> None:
        """
        Triangulate all faces of a mesh.
        
        Args:
            obj: Mesh object to triangulate
            
        Raises:
            TypeError: If object is not a mesh
            
        Example:
            >>> ClusterPreprocessor.triangulate_mesh(mesh_obj)
        """
        if obj.type != 'MESH':
            raise TypeError(f"Object '{obj.name}' is not a mesh")
        
        logger.info(f"Triangulating mesh: {obj.name}")
        
        # Ensure Object mode
        if bpy.context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        
        # Set as active
        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        
        mesh = obj.data
        bm = bmesh.new()
        bm.from_mesh(mesh)
        
        # Triangulate
        bmesh.ops.triangulate(bm, faces=bm.faces[:])
        
        bm.to_mesh(mesh)
        bm.free()
        mesh.update()
        
        logger.info(f"  ✓ Mesh triangulated ({len(mesh.polygons)} faces)")
    
    
    @staticmethod
    def preprocess_cluster(
        mesh_list: List[bpy.types.Object],
        cluster_name: str = "ProcessedCluster",
        merge_distance: float = DEFAULT_MERGE_DISTANCE,
        triangulate: bool = True
    ) -> bpy.types.Object:
        """
        Complete preprocessing pipeline for a cluster:
        1. Join all meshes
        2. Merge boundary vertices
        3. Clean geometry
        4. Optionally triangulate
        
        This is the main function you should use for cluster preprocessing.
        
        Args:
            mesh_list: List of mesh objects in the cluster
            cluster_name: Name for the processed cluster
            merge_distance: Distance threshold for merging vertices
            triangulate: Whether to triangulate the mesh
            
        Returns:
            The preprocessed mesh object
            
        Example:
            >>> # Process a cluster of meshes
            >>> cluster_meshes = [mesh1, mesh2, mesh3]
            >>> processed = ClusterPreprocessor.preprocess_cluster(
            ...     mesh_list=cluster_meshes,
            ...     cluster_name="Material_001_Processed",
            ...     triangulate=True
            ... )
        """
        logger.info("=" * 80)
        logger.info(f"PREPROCESSING CLUSTER: {cluster_name}")
        logger.info("=" * 80)
        
        # Step 1: Join meshes
        joined_mesh = ClusterPreprocessor.join_cluster_meshes(
            mesh_list=mesh_list,
            cluster_name=cluster_name,
            merge_distance=merge_distance
        )
        
        # Step 2: Clean geometry
        ClusterPreprocessor.clean_geometry(
            obj=joined_mesh,
            remove_loose=False,
            fix_non_manifold=False,
            merge_distance=merge_distance
        )
        
        # Step 3: Optionally triangulate
        if triangulate:
            ClusterPreprocessor.triangulate_mesh(joined_mesh)
        
        logger.info("=" * 80)
        logger.info(f"✓ CLUSTER PREPROCESSING COMPLETED: {cluster_name}")
        logger.info("=" * 80)
        
        return joined_mesh
    
    
    @staticmethod
    def preprocess_all_clusters(
        clusters: Dict[str, List[bpy.types.Object]],
        merge_distance: float = DEFAULT_MERGE_DISTANCE,
        triangulate: bool = False
    ) -> Dict[str, bpy.types.Object]:
        """
        Preprocess all clusters in a dictionary.
        
        Args:
            clusters: Dictionary mapping material names to mesh lists
            merge_distance: Distance threshold for merging vertices
            triangulate: Whether to triangulate meshes
            
        Returns:
            Dictionary mapping material names to preprocessed mesh NAMES (strings)
            
        Example:
            >>> # Get clusters from MeshClusterManager
            >>> from scene_manager import MeshClusterManager
            >>> clusters = MeshClusterManager.cluster_by_material()
            >>> 
            >>> # Preprocess all clusters
            >>> processed = ClusterPreprocessor.preprocess_all_clusters(clusters)
            >>> 
            >>> # Now you have mesh names (strings)
            >>> for material_name, mesh_name in processed.items():
            >>>     print(f"{material_name}: {mesh_name}")
            >>>     # Get the actual object if needed:
            >>>     mesh_obj = bpy.data.objects[mesh_name]
        """
        logger.info("\n" + "=" * 80)
        logger.info(f"PREPROCESSING {len(clusters)} CLUSTERS")
        logger.info("=" * 80)
        
        processed_clusters = {}
        
        for material_name, mesh_list in clusters.items():
            # Skip empty clusters
            if not mesh_list:
                logger.warning(f"Skipping empty cluster: {material_name}")
                continue
            
            # Sanitize material name for object name
            safe_name = material_name.replace(" ", "_").replace("/", "_").replace(".", "_")
            cluster_name = f"Cluster_{safe_name}"
            
            # Preprocess cluster
            processed_mesh = ClusterPreprocessor.preprocess_cluster(
                mesh_list=mesh_list,
                cluster_name=cluster_name,
                merge_distance=merge_distance,
                triangulate=triangulate
            )
            
            # Store only the mesh NAME (string), not the bpy_struct object
            processed_clusters[material_name] = processed_mesh
            
            logger.info("")  # Empty line for readability
        
        logger.info("=" * 80)
        logger.info(f"✓ ALL CLUSTERS PREPROCESSED ({len(processed_clusters)} total)")
        logger.info("=" * 80)
        
        return processed_clusters
