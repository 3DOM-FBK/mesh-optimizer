import bpy
import logging

# Base logging configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SceneHelper:
    """
    Helper class for Blender scene management.
    """

    @staticmethod
    def cleanup_scene():
        """
        Cleanups completely the current scene removing:
        - All objects (MESH, LIGHT, CAMERA, etc.)
        - All collections (except Master Collection if not removable)
        - All orphan data (Mesh, Materials, Textures, Lights, Cameras, Curves, etc.)
        
        The goal is to get a 'tabula rasa' state.
        """
        logger.info("Starting complete scene cleanup...")

        # 1. Remove all objects from scene
        if bpy.context.view_layer.objects:
            bpy.ops.object.select_all(action='SELECT')
            bpy.ops.object.delete(use_global=False)
        
        # 2. Remove all collections (expect main Scene Collection)
        for collection in bpy.data.collections:
            bpy.data.collections.remove(collection)

        # 3. Purge orphan data-blocks
        # Iterate over all data collections and remove if no users
        # Note: Order is important for dependencies (e.g. materials used by mesh)
        
        # Delete meshes
        for mesh in bpy.data.meshes:
            bpy.data.meshes.remove(mesh)

        # Delete materials
        for mat in bpy.data.materials:
            bpy.data.materials.remove(mat)

        # Delete textures
        for tex in bpy.data.textures:
            bpy.data.textures.remove(tex)
            
        # Delete images
        for img in bpy.data.images:
            bpy.data.images.remove(img)

        # Delete lights
        for light in bpy.data.lights:
            bpy.data.lights.remove(light)

        # Delete cameras
        for camera in bpy.data.cameras:
            bpy.data.cameras.remove(camera)
            
        # Delete curves
        for curve in bpy.data.curves:
            bpy.data.curves.remove(curve)

        # Final 'purge' via orphan operator to be safe (multiple cycles for nested dependencies)
        for _ in range(3):
            bpy.ops.outliner.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=True)

        logger.info("Scene cleaned successfully.")

    @staticmethod
    def remove_all_materials(obj: bpy.types.Object):
        """
        Removes all materials assigned to the specified object and cleans
        linked textures/images if no longer used.
        
        Args:
            obj (bpy.types.Object): Mesh object from which to remove materials.
        """
        if obj.type != 'MESH':
            logger.warning(f"Object '{obj.name}' is not a mesh. Cannot remove materials.")
            return

        logger.info(f"Removing materials and associated textures from: {obj.name}")
        
        # Identify unique materials used by this object before detaching
        used_materials = {slot.material for slot in obj.material_slots if slot.material}
        
        # Remove materials from object
        obj.data.materials.clear()
        
        # Targeted cleanup: Remove materials became orphans and their images
        for mat in used_materials:
            # Note: mat.users might not update instantly without trigger,
            # but after .clear() usually it is. If > 0 means used elsewhere.
            if mat.users == 0:
                # Search images in node tree before removing material block
                images_to_check = set()
                if mat.use_nodes and mat.node_tree:
                    for node in mat.node_tree.nodes:
                        if node.type == 'TEX_IMAGE' and node.image:
                            images_to_check.add(node.image)
                            
                logger.info(f"Removing orphan material: {mat.name}")
                bpy.data.materials.remove(mat)
                
                # Check and remove images became orphans
                for img in images_to_check:
                    if img.users == 0:
                        logger.info(f"Removing orphan image: {img.name}")
                        bpy.data.images.remove(img)

    @staticmethod
    def cleanup_scene_except(keep_obj: bpy.types.Object):
        """
        Cleans the scene removing everything EXCEPT the specified object.
        Also removes materials and textures not used by the kept object (via orphan purge).
        
        Args:
            keep_obj (bpy.types.Object): The object to preserve.
        """
        logger.info(f"Scene cleanup preserving only: {keep_obj.name}")
        
        # 1. Remove all objects except the one to keep
        bpy.ops.object.select_all(action='DESELECT')
        
        objs_to_remove = [o for o in bpy.context.scene.objects if o != keep_obj]
        
        if objs_to_remove:
            for o in objs_to_remove:
                o.select_set(True)
            bpy.ops.object.delete()
            
        # 2. Remove empty collections (optional, but clean)
        # Don't remove master collection or where object resides
        # For simplicity, purge orphans handles data, empty collections don't weigh much.
        
        # 3. Purge Orphans to remove Mesh, Materials and Textures no longer used
        # Since we deleted objects using 'old' materials,
        # purge will find them as orphans (0 users) and remove them.
        # Materials of 'keep_obj' still have 1 user, so they remain.
        for _ in range(3):
            bpy.ops.outliner.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=True)
            
        logger.info("Partial cleanup completed.")
