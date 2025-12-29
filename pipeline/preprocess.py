import bpy
import bmesh
import logging

# Base logging configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MeshPreprocessor:
    """
    Class for mesh preprocessing in Blender:
    - Merging multiple meshes by material
    - Non-manifold geometry fix
    - Loose geometry removal
    - Triangulation
    """

    @staticmethod
    def _set_active_object(obj):
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)

    @staticmethod
    def _get_material_key(obj):
        """
        Generates a unique key for an object's material.
        If object has multiple materials, uses the first one.
        If no material, returns 'NO_MATERIAL'.
        """
        if obj.data.materials:
            mat = obj.data.materials[0]
            return mat.name if mat else 'NO_MATERIAL'
        return 'NO_MATERIAL'

    @staticmethod
    def group_by_material(root_name: str) -> dict:
        """
        Groups all mesh objects under root_name by material.
        
        Returns:
            dict: Dictionary {material_name: [list of objects]}
        """
        root = bpy.data.objects.get(root_name)
        if root is None:
            logger.error(f"Root object '{root_name}' not found")
            return {}

        meshes = [obj for obj in root.children_recursive if obj.type == 'MESH']
        
        # Add root if it is a mesh
        if root.type == 'MESH':
            meshes.append(root)

        if not meshes:
            logger.error("No mesh objects found under the root")
            return {}

        # Group by material
        material_groups = {}
        for mesh in meshes:
            mat_key = MeshPreprocessor._get_material_key(mesh)
            if mat_key not in material_groups:
                material_groups[mat_key] = []
            material_groups[mat_key].append(mesh)

        logger.info(f"Found {len(material_groups)} material groups:")
        for mat_name, objs in material_groups.items():
            logger.info(f"  - {mat_name}: {len(objs)} objects")

        return material_groups

    @staticmethod
    def flatten_and_join_by_material(root_name: str, merge_vertices_threshold: float = None) -> list[bpy.types.Object]:
        """
        Joins all meshes under root_name grouping them by material.
        
        Returns:
            list: List of joined mesh objects, one per material
        """
        material_groups = MeshPreprocessor.group_by_material(root_name)
        
        if not material_groups:
            return []

        joined_meshes = []

        for mat_name, meshes in material_groups.items():
            logger.info(f"Processing material group: {mat_name} ({len(meshes)} objects)")
            
            # Safe flatten: unparent keeping world transform
            for mesh in meshes:
                world_mat = mesh.matrix_world.copy()
                mesh.parent = None
                mesh.matrix_world = world_mat

            # Deselect all
            bpy.ops.object.select_all(action='DESELECT')

            # Select all meshes in this group
            for mesh in meshes:
                mesh.select_set(True)

            # Make one active
            bpy.context.view_layer.objects.active = meshes[0]

            # Join meshes
            bpy.ops.object.join()
            combined_mesh = bpy.context.view_layer.objects.active
            
            # Rename joined object
            combined_mesh.name = f"Joined_{mat_name}"

            # Merge vertices if threshold is provided
            if merge_vertices_threshold is not None:
                bpy.ops.object.mode_set(mode='EDIT')
                bpy.ops.mesh.select_all(action='SELECT')
                bpy.ops.mesh.remove_doubles(threshold=merge_vertices_threshold)
                bpy.ops.object.mode_set(mode='OBJECT')

            joined_meshes.append(combined_mesh)
            logger.info(f"  -> Created: {combined_mesh.name}")

        return joined_meshes

    @staticmethod
    def flatten_and_join(root_name: str, merge_vertices_threshold: float = None) -> bpy.types.Object:
        """
        Flatten the hierarchy under `root_name` by removing all parents,
        applying parent transforms, and joining all meshes into a single one.
        Optionally merge vertices by distance.
        
        NOTE: This method joins EVERYTHING into a SINGLE mesh.
        To keep materials separated, use flatten_and_join_by_material()
        """
        root = bpy.data.objects.get(root_name)
        if root is None:
            logger.error(f"Root object '{root_name}' not found")
            return None

        meshes = [obj for obj in root.children_recursive if obj.type == 'MESH']
        
        # Add root if it is a mesh
        if root.type == 'MESH':
            meshes.append(root)

        if not meshes:
            logger.error("No mesh objects found under the root")
            return None

        # Safe flatten: unparent keeping world transform
        for mesh in meshes:
            world_mat = mesh.matrix_world.copy()
            mesh.parent = None
            mesh.matrix_world = world_mat

        # Deselect all
        bpy.ops.object.select_all(action='DESELECT')

        # Select all meshes
        for mesh in meshes:
            mesh.select_set(True)

        # Make one active
        bpy.context.view_layer.objects.active = meshes[0]

        # Join meshes
        bpy.ops.object.join()
        combined_mesh = bpy.context.view_layer.objects.active
        
        if merge_vertices_threshold is not None:
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.select_all(action='SELECT')
            bpy.ops.mesh.remove_doubles(threshold=merge_vertices_threshold)
            bpy.ops.object.mode_set(mode='OBJECT')

        return combined_mesh

    @staticmethod
    def clean_and_fix(obj: bpy.types.Object):
        """
        Performs mesh cleanup:
        1. Select & Fix non-manifold (merge doubles, fill simple holes)
        2. Remove loose geometry
        3. Triangulation
        """
        if obj is None or obj.type != 'MESH':
            logger.warning("Object not valid for preprocessing.")
            return

        logger.info(f"Starting mesh cleanup for: {obj.name}")
        
        MeshPreprocessor._set_active_object(obj)
        
        # Switch to Edit Mode
        bpy.ops.object.mode_set(mode='EDIT')
        
        # 1. Merge by distance (Remove Doubles) - Often fixes basic non-manifold
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.remove_doubles(threshold=0.0001)
        
        # # 2. Fix Non-Manifold (Hole filling attempt)
        # bpy.ops.mesh.select_all(action='DESELECT')
        # bpy.ops.mesh.select_non_manifold()
        # bpy.ops.mesh.fill_holes(sides=0) # 0 = infinite sides allowed
        
        # 3. Remove Loose Geometry (isolated vertices/edges/faces)
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.delete_loose()
        
        # 4. Recalculate normals and remove sharp edges
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.mark_sharp(clear=True)
        # Clear custom split normals if present
        if obj.data.has_custom_normals:
             bpy.ops.mesh.customdata_custom_splitnormals_clear()
             
        bpy.ops.mesh.normals_make_consistent(inside=False)

        # 5. Triangulate
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.quads_convert_to_tris(quad_method='BEAUTY', ngon_method='BEAUTY')
        
        # Return to Object Mode
        bpy.ops.object.mode_set(mode='OBJECT')
        
        logger.info(f"Preprocessing completed for: {obj.name}")

    @staticmethod
    def process_by_material(root_name: str, merge_vertices_threshold: float = None) -> list[bpy.types.Object]:
        """
        Main pipeline to process while keeping materials separated:
        1. Group by material
        2. Join for each group
        3. Clean & Triangulate each mesh
        
        Returns:
            list: List of processed mesh objects, one for each material
        """
        # 1. Join by material
        joined_meshes = MeshPreprocessor.flatten_and_join_by_material(
            root_name, 
            merge_vertices_threshold
        )
        
        if not joined_meshes:
            logger.warning("No meshes to process")
            return []
        
        # 2. Clean, Fix & Triangulate each mesh
        for mesh in joined_meshes:
            MeshPreprocessor.clean_and_fix(mesh)
        
        logger.info(f"Process completed: {len(joined_meshes)} final meshes")
        return joined_meshes

    @staticmethod
    def process(root_name: str, merge_vertices_threshold: float = None) -> bpy.types.Object:
        """
        Original main pipeline: Join everything -> Clean -> Triangulate
        
        DEPRECATED: Use process_by_material() to keep materials separated
        
        Returns the final processed object.
        """
        logger.warning("Warning: process() joins everything into a single mesh. Use process_by_material() to keep materials separated.")
        
        # 1. Join (Flatten) everything
        final_mesh = MeshPreprocessor.flatten_and_join(root_name, merge_vertices_threshold)
        
        if final_mesh is None:
            return None
        
        # 2. Clean, Fix & Triangulate
        MeshPreprocessor.clean_and_fix(final_mesh)
        
        return final_mesh