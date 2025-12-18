"""
Scene Manager Module

Manages the cleanup and reset of the Blender scene.
Essential for maintaining a clean state when processing multiple meshes.
"""

import bpy
from typing import Optional, List
import sys
import os


class SceneManager:
    """
    Manages the Blender scene and provides comprehensive cleanup functionality.

    This class is essential when working with pipelines that process
    multiple meshes or when a clean scene state needs to be ensured.
    """

    @staticmethod
    def cleanup_scene(
        keep_camera: bool = False,
        keep_lights: bool = False,
        remove_orphan_data: bool = True,
        reset_world: bool = False
    ) -> None:
        """
        Completely cleans the Blender scene by removing all objects and orphan data.

        This function performs a complete cleanup of the Blender scene:
        1. Removes all objects (meshes, curves, armatures, etc.)
        2. Optionally keeps cameras and lights
        3. Removes orphan data (meshes, materials, textures, images with no users)
        4. Optionally resets world settings

        Args:
            keep_camera: If True, keeps camera objects
            keep_lights: If True, keeps light objects
            remove_orphan_data: If True, removes all data with no users
            reset_world: If True, resets world settings (background, etc.)

        Example:
            >>> # Complete cleanup
            >>> SceneManager.cleanup_scene()

            >>> # Keep camera and lights for rendering
            >>> SceneManager.cleanup_scene(keep_camera=True, keep_lights=True)
        """

        # ===== STEP 1: Remove objects from the scene =====

        # Ensure we are in Object mode
        if bpy.context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        # Select all objects
        bpy.ops.object.select_all(action='SELECT')

        # Deselect objects to keep
        objects_to_keep = []
        if keep_camera or keep_lights:
            for obj in bpy.context.selected_objects[:]:
                if keep_camera and obj.type == 'CAMERA':
                    obj.select_set(False)
                    objects_to_keep.append(obj.name)
                elif keep_lights and obj.type == 'LIGHT':
                    obj.select_set(False)
                    objects_to_keep.append(obj.name)

        # Count objects to remove
        objects_to_remove = len(bpy.context.selected_objects)

        # Remove selected objects
        if objects_to_remove > 0:
            bpy.ops.object.delete()

        # ===== STEP 2: Remove orphan data =====
        if remove_orphan_data:

            # Remove orphan meshes
            for mesh in list(bpy.data.meshes):
                if mesh.users == 0:
                    bpy.data.meshes.remove(mesh)

            # Remove orphan materials
            for material in list(bpy.data.materials):
                if material.users == 0:
                    bpy.data.materials.remove(material)

            # Remove orphan textures
            for texture in list(bpy.data.textures):
                if texture.users == 0:
                    bpy.data.textures.remove(texture)

            # Remove orphan images (but keep packed ones)
            for image in list(bpy.data.images):
                if image.users == 0 and not image.packed_file:
                    bpy.data.images.remove(image)

            # Remove orphan curves
            for curve in list(bpy.data.curves):
                if curve.users == 0:
                    bpy.data.curves.remove(curve)

            # Remove orphan armatures
            for armature in list(bpy.data.armatures):
                if armature.users == 0:
                    bpy.data.armatures.remove(armature)

            # Remove orphan node groups
            for node_group in list(bpy.data.node_groups):
                if node_group.users == 0:
                    bpy.data.node_groups.remove(node_group)

            # Remove orphan actions
            for action in list(bpy.data.actions):
                if action.users == 0:
                    bpy.data.actions.remove(action)

        # ===== STEP 3: Clean collections =====

        # Remove empty collections (except Master Collection)
        for collection in list(bpy.data.collections):
            if len(collection.objects) == 0 and len(collection.children) == 0:
                bpy.data.collections.remove(collection)

        # ===== STEP 4: Reset world (optional) =====
        if reset_world:

            # Create or reset the world
            if bpy.context.scene.world is None:
                bpy.context.scene.world = bpy.data.worlds.new("World")

            world = bpy.context.scene.world

            # Reset background color
            if world.use_nodes:
                # If using nodes, reset the Background node
                for node in world.node_tree.nodes:
                    if node.type == 'BACKGROUND':
                        node.inputs['Color'].default_value = (0.05, 0.05, 0.05, 1.0)
                        node.inputs['Strength'].default_value = 1.0
            else:
                # Otherwise use direct color
                world.color = (0.05, 0.05, 0.05)


    @staticmethod
    def ensure_object_mode() -> None:
        """
        Ensures Blender is in Object mode.

        Useful before operations that require Object mode.
        """
        if bpy.context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')


    @staticmethod
    def set_active_object(obj: bpy.types.Object) -> None:
        """
        Sets an object as active in the scene.

        Args:
            obj: The Blender object to make active
        """
        SceneManager.ensure_object_mode()
        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj


        return [obj for obj in bpy.data.objects if obj.type == 'MESH']
    
    
    @staticmethod
    def cleanup_keep_meshes(
        meshes_to_keep: List[bpy.types.Object],
        remove_orphan_data: bool = True
    ) -> None:
        """
        Clean up scene keeping only specified meshes and their materials.
        
        This function removes all objects from the scene EXCEPT the specified meshes,
        and cleans up all orphan data (meshes, materials, textures, etc.) while
        preserving the materials assigned to the kept meshes.
        
        If meshes_to_keep is empty, this function will clean the ENTIRE scene
        (equivalent to cleanup_scene()).
        
        Args:
            meshes_to_keep: List of mesh objects to keep in the scene.
                          If empty, cleans entire scene.
            remove_orphan_data: If True, removes all orphan data blocks
            
        Example:
            >>> # Keep only processed cluster meshes
            >>> cluster_meshes = [mesh1, mesh2, mesh3]
            >>> SceneManager.cleanup_keep_meshes(cluster_meshes)
            
            >>> # Clean entire scene
            >>> SceneManager.cleanup_keep_meshes([])
            
            >>> # Keep specific meshes by name
            >>> meshes = [bpy.data.objects[name] for name in ['Cluster_Mat1', 'Cluster_Mat2']]
            >>> SceneManager.cleanup_keep_meshes(meshes)
        """
        # Ensure Object mode
        if bpy.context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        
        # Get names of meshes to keep (for safety)
        keep_names = {mesh.name for mesh in meshes_to_keep if mesh.type == 'MESH'}
        
        # If empty, clean entire scene
        if not keep_names:
            # Use the full cleanup_scene function
            SceneManager.cleanup_scene(
                keep_camera=False,
                keep_lights=False,
                remove_orphan_data=remove_orphan_data,
                reset_world=False
            )
            return
        
        # Collect materials used by meshes to keep
        materials_to_keep = set()
        for mesh in meshes_to_keep:
            if mesh.type == 'MESH' and mesh.data.materials:
                for mat in mesh.data.materials:
                    if mat is not None:
                        materials_to_keep.add(mat.name)
        
        # ===== STEP 1: Remove all objects except the ones to keep =====
        
        # Deselect all
        bpy.ops.object.select_all(action='DESELECT')
        
        # Select all objects EXCEPT the ones to keep
        objects_to_remove = []
        for obj in bpy.data.objects:
            if obj.name not in keep_names:
                obj.select_set(True)
                objects_to_remove.append(obj.name)
        
        # Delete selected objects
        if objects_to_remove:
            bpy.ops.object.delete()
        
        # ===== STEP 2: Remove orphan data (if requested) =====
        if remove_orphan_data:
            
            # Remove orphan meshes (but NOT the ones we're keeping)
            for mesh_data in list(bpy.data.meshes):
                if mesh_data.users == 0:
                    bpy.data.meshes.remove(mesh_data)
            
            # Remove orphan materials (but NOT the ones used by kept meshes)
            for material in list(bpy.data.materials):
                if material.users == 0 and material.name not in materials_to_keep:
                    bpy.data.materials.remove(material)
            
            # Remove orphan textures
            for texture in list(bpy.data.textures):
                if texture.users == 0:
                    bpy.data.textures.remove(texture)
            
            # Remove orphan images (but keep packed ones)
            for image in list(bpy.data.images):
                if image.users == 0 and not image.packed_file:
                    bpy.data.images.remove(image)
            
            # Remove orphan curves
            for curve in list(bpy.data.curves):
                if curve.users == 0:
                    bpy.data.curves.remove(curve)
            
            # Remove orphan armatures
            for armature in list(bpy.data.armatures):
                if armature.users == 0:
                    bpy.data.armatures.remove(armature)
            
            # Remove orphan node groups
            for node_group in list(bpy.data.node_groups):
                if node_group.users == 0:
                    bpy.data.node_groups.remove(node_group)
            
            # Remove orphan actions
            for action in list(bpy.data.actions):
                if action.users == 0:
                    bpy.data.actions.remove(action)
        
        # ===== STEP 3: Clean collections =====
        
        # Remove empty collections (except Master Collection)
        for collection in list(bpy.data.collections):
            if len(collection.objects) == 0 and len(collection.children) == 0:
                bpy.data.collections.remove(collection)



# ==============================================================================
# Mesh Cluster Manager
# ==============================================================================

class MeshClusterManager:
    """
    Manages mesh clustering based on materials.
    
    This class provides functionality to group meshes by their assigned materials,
    which is useful for batch processing, material-based optimization, or
    organizing complex scenes with multiple mesh clusters.
    """
    
    @staticmethod
    def cluster_by_material(
        meshes: Optional[List[bpy.types.Object]] = None,
        include_no_material: bool = True
    ) -> dict:
        """
        Clusters meshes by their assigned materials.
        
        Groups mesh objects based on the materials they use. Meshes with the same
        material(s) are grouped together. This is useful for:
        - Batch processing meshes with the same material
        - Material-based optimization
        - Understanding material distribution in the scene
        
        Args:
            meshes: List of mesh objects to cluster. If None, uses all meshes in scene.
            include_no_material: If True, includes meshes without materials in results.
        
        Returns:
            Dictionary mapping material names to lists of mesh objects:
            {
                'MaterialName1': [mesh1, mesh2, mesh3],
                'MaterialName2': [mesh4, mesh5],
                'NO_MATERIAL': [mesh6]  # Only if include_no_material=True
            }
        
        Example:
            >>> # Cluster all meshes in scene
            >>> clusters = MeshClusterManager.cluster_by_material()
            >>> for material_name, mesh_list in clusters.items():
            >>>     print(f"{material_name}: {len(mesh_list)} meshes")
            
            >>> # Cluster specific meshes
            >>> selected_meshes = [obj for obj in bpy.context.selected_objects if obj.type == 'MESH']
            >>> clusters = MeshClusterManager.cluster_by_material(meshes=selected_meshes)
        """
        # Get meshes to process
        if meshes is None:
            meshes = [obj for obj in bpy.data.objects if obj.type == 'MESH']
        
        # Dictionary to store clusters: {material_name: [mesh_objects]}
        material_clusters = {}
        
        # Process each mesh
        for mesh_obj in meshes:
            # Get materials assigned to this mesh
            materials = mesh_obj.data.materials
            
            if len(materials) == 0:
                # Mesh has no materials
                if include_no_material:
                    if 'NO_MATERIAL' not in material_clusters:
                        material_clusters['NO_MATERIAL'] = []
                    material_clusters['NO_MATERIAL'].append(mesh_obj)
            else:
                # Mesh has materials - add to each material's cluster
                for material in materials:
                    if material is not None:
                        mat_name = material.name
                        if mat_name not in material_clusters:
                            material_clusters[mat_name] = []
                        material_clusters[mat_name].append(mesh_obj)
        
        return material_clusters
    
    
    @staticmethod
    def cluster_by_single_material(
        meshes: Optional[List[bpy.types.Object]] = None,
        include_no_material: bool = True
    ) -> dict:
        """
        Clusters meshes by their PRIMARY material (first material slot).
        
        Unlike cluster_by_material(), this only considers the first material slot.
        Useful when you want each mesh to belong to exactly one cluster.
        
        Args:
            meshes: List of mesh objects to cluster. If None, uses all meshes in scene.
            include_no_material: If True, includes meshes without materials.
        
        Returns:
            Dictionary mapping material names to lists of mesh objects.
        
        Example:
            >>> clusters = MeshClusterManager.cluster_by_single_material()
            >>> # Each mesh appears in exactly one cluster
        """
        if meshes is None:
            meshes = [obj for obj in bpy.data.objects if obj.type == 'MESH']
        
        material_clusters = {}
        
        for mesh_obj in meshes:
            materials = mesh_obj.data.materials
            
            if len(materials) == 0:
                # No materials
                if include_no_material:
                    if 'NO_MATERIAL' not in material_clusters:
                        material_clusters['NO_MATERIAL'] = []
                    material_clusters['NO_MATERIAL'].append(mesh_obj)
            else:
                # Use first material only
                material = materials[0]
                if material is not None:
                    mat_name = material.name
                    if mat_name not in material_clusters:
                        material_clusters[mat_name] = []
                    material_clusters[mat_name].append(mesh_obj)
                else:
                    # First slot is None
                    if include_no_material:
                        if 'NO_MATERIAL' not in material_clusters:
                            material_clusters['NO_MATERIAL'] = []
                        material_clusters['NO_MATERIAL'].append(mesh_obj)
        
        return material_clusters
    
    
    @staticmethod
    def get_cluster_statistics(clusters: dict) -> dict:
        """
        Get statistics about material clusters.
        
        Args:
            clusters: Dictionary from cluster_by_material() or cluster_by_single_material()
        
        Returns:
            Dictionary with statistics:
            {
                'total_materials': int,
                'total_meshes': int,
                'largest_cluster': {'material': str, 'count': int},
                'smallest_cluster': {'material': str, 'count': int},
                'average_cluster_size': float,
                'details': [{'material': str, 'mesh_count': int, 'mesh_names': [str]}]
            }
        
        Example:
            >>> clusters = MeshClusterManager.cluster_by_material()
            >>> stats = MeshClusterManager.get_cluster_statistics(clusters)
            >>> print(f"Total materials: {stats['total_materials']}")
            >>> print(f"Largest cluster: {stats['largest_cluster']['material']} ({stats['largest_cluster']['count']} meshes)")
        """
        if not clusters:
            return {
                'total_materials': 0,
                'total_meshes': 0,
                'largest_cluster': None,
                'smallest_cluster': None,
                'average_cluster_size': 0,
                'details': []
            }
        
        # Calculate statistics
        total_materials = len(clusters)
        total_meshes = sum(len(meshes) for meshes in clusters.values())
        
        # Find largest and smallest clusters
        cluster_sizes = {mat: len(meshes) for mat, meshes in clusters.items()}
        largest_mat = max(cluster_sizes, key=cluster_sizes.get)
        smallest_mat = min(cluster_sizes, key=cluster_sizes.get)
        
        # Calculate average
        average_size = total_meshes / total_materials if total_materials > 0 else 0
        
        # Build details
        details = []
        for material_name, mesh_list in sorted(clusters.items(), key=lambda x: len(x[1]), reverse=True):
            details.append({
                'material': material_name,
                'mesh_count': len(mesh_list),
                'mesh_names': [mesh.name for mesh in mesh_list]
            })
        
        return {
            'total_materials': total_materials,
            'total_meshes': total_meshes,
            'largest_cluster': {
                'material': largest_mat,
                'count': cluster_sizes[largest_mat]
            },
            'smallest_cluster': {
                'material': smallest_mat,
                'count': cluster_sizes[smallest_mat]
            },
            'average_cluster_size': average_size,
            'details': details
        }