import bpy
import logging

# Logging configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class UVPacker:
    """
    Class to handle UV islands packing using Blender's operators.
    """

    @staticmethod
    def pack_islands(obj: bpy.types.Object, margin: float = 0.001):
        """
        Applies Blender's 'Pack Islands' operator to all UVs of the object.
        
        Args:
            obj (bpy.types.Object): Mesh object with UV map.
            margin (float): Margin between islands (in UV space 0-1).
            
        Returns:
            bool: True if successful, False otherwise.
        """
        if obj.type != 'MESH':
            logger.error(f"Object {obj.name} is not a mesh.")
            return False
            
        # Ensure object is active and selected
        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        
        # Switch to Edit Mode
        bpy.ops.object.mode_set(mode='EDIT')
        
        # Select all faces to include all UVs in packing
        bpy.ops.mesh.select_all(action='SELECT')
        
        # Select all UV vertices in UV Editor (required for pack_islands)
        # Note: bpy.ops.uv.select_all works on UV/Image Editor context.
        # In background mode might require context override if not working directly.
        # However, standard pack_islands often acts on current mesh selection if 'rotate' etc are true.
        
        logger.info(f"Starting UV Packing for {obj.name} with margin {margin}...")
        
        try:
            # Executes packing
            # Parameters:
            # - margin: space between islands
            # - rotate: allows rotation for better fit (default True)
            bpy.ops.uv.pack_islands(margin=margin, rotate=True) # PartUV already orients charts? If yes, rotate=False.
            # If PartUV generates charts randomly oriented, better rotate=True.
            
            # Return to Object Mode
            bpy.ops.object.mode_set(mode='OBJECT')
            logger.info("UV Packing completed.")
            return True
            
        except Exception as e:
            logger.error(f"Error during UV Packing: {e}")
            # Ensure exit from Edit Mode even on error
            if bpy.context.object.mode == 'EDIT':
                bpy.ops.object.mode_set(mode='OBJECT')
            return False
