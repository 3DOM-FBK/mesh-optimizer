import bpy
import os
import logging
from typing import List, Optional, Union

# Base logging configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MeshIO:
    """
    Helper class for mesh import and export (OBJ, GLB) using Blender (bpy).
    """

    @staticmethod
    def load(file_path: str) -> List[bpy.types.Object]:
        """
        Loads a mesh from file into Blender scene.
        Cleans the scene before loading (Note: verify if cleanup is desired logic here or external).
        Wait, original code did NOT clean scene inside load used in pipeline context probably? 
        Actually original comment said "Pulisce la scena prima del caricamento" 
        but implementation DOES NOT call cleanup_scene(). 
        It just imports. I will keep implementation logic.
        
        Args:
            file_path (str): Absolute path of file to load.
            
        Returns:
            List[bpy.types.Object]: List of imported mesh objects.
        """
        if not os.path.exists(file_path):
            logger.error(f"File not found: {file_path}")
            return []

        ext = os.path.splitext(file_path)[1].lower()
        try:
            if ext == '.obj':
                # Blender 4.0+ uses wm.obj_import by default (faster, C++)
                if hasattr(bpy.ops.wm, 'obj_import'):
                    bpy.ops.wm.obj_import(filepath=file_path)
                else:
                    # Fallback for previous versions
                    bpy.ops.import_scene.obj(filepath=file_path)
                    
            elif ext in ['.glb', '.gltf']:
                bpy.ops.import_scene.gltf(filepath=file_path)
            else:
                logger.error(f"Format not supported: {ext}")
                return []

            # Collect imported objects (assuming they are selected after import)
            # Note: some importers automatically select objects.
            imported_objects = [obj for obj in bpy.context.selected_objects if obj.type == 'MESH']
            
            # If no object is selected, try taking all meshes in scene (risky if scene not empty)
            if not imported_objects:
                imported_objects = [obj for obj in bpy.context.scene.objects if obj.type == 'MESH']

            logger.info(f"Imported {file_path} with {len(imported_objects)} mesh objects.")
            return imported_objects

        except Exception as e:
            logger.error(f"Error during import of {file_path}: {e}")
            return []

    @staticmethod
    def export(output_path: str, objects: Optional[List[bpy.types.Object]] = None) -> bool:
        """
        Exports specified objects (or currently selected ones) to file.
        
        Args:
            output_path (str): Destination path.
            objects (List[bpy.types.Object], optional): List of objects to export. 
                                                        If None, exports current selection.
            
        Returns:
            bool: True if export successful, False otherwise.
        """
        try:
            # Create output directory if not exists
            output_dir = os.path.dirname(output_path)
            if output_dir and not os.path.exists(output_dir):
                os.makedirs(output_dir)

            # Selection management
            if objects is not None:
                bpy.ops.object.select_all(action='DESELECT')
                for obj in objects:
                    obj.select_set(True)
            
            # If still nothing selected, select all meshes
            if not bpy.context.selected_objects:
                for obj in bpy.context.scene.objects:
                    if obj.type == 'MESH':
                        obj.select_set(True)

            ext = os.path.splitext(output_path)[1].lower()
            
            if ext == '.obj':
                if hasattr(bpy.ops.wm, 'obj_export'):
                    bpy.ops.wm.obj_export(filepath=output_path, export_selected_objects=True)
                else:
                    bpy.ops.export_scene.obj(filepath=output_path, use_selection=True)
                    
            elif ext in ['.glb', '.gltf']:
                bpy.ops.export_scene.gltf(filepath=output_path, use_selection=True)
            else:
                logger.error(f"Extension not recognized for export: {ext}")
                return False

            logger.info(f"Export completed in: {output_path}")
            return True

        except Exception as e:
            logger.error(f"Error during export in {output_path}: {e}")
            return False

    @staticmethod
    def save_images_to_dir(images_dict: dict, output_dir: str, format: str = 'PNG') -> List[str]:
        """
        Saves a dictionary of bpy.types.Image objects to disk.
        
        Args:
            images_dict (dict): { 'map_name': bpy.types.Image }
            output_dir (str): Destination directory.
            format (str): File format (PNG, JPEG, etc.).
            
        Returns:
            List[str]: List of saved file paths.
        """
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            
        logger.info(f"Saving {len(images_dict)} images to {output_dir}")
        saved_paths = []
        
        # Save original render settings state to restore
        orig_format = bpy.context.scene.render.image_settings.file_format
        # orig_depth = bpy.context.scene.render.image_settings.color_depth

        bpy.context.scene.render.image_settings.file_format = format
        # Optional: 16 bit for data maps if needed, but png 8 bit is standard for web/GLB.
        # bpy.context.scene.render.image_settings.color_depth = '16' 

        for map_name, img in images_dict.items():
            if not img: continue
            
            # Construct filename
            filename = f"{map_name}.{format.lower()}"
            filepath = os.path.join(output_dir, filename)
            
            # Set filepath on image for save_render
            # Note: save_render uses scene settings (so uses the path we give in filepath)
            # But img.save() uses img.filepath_raw and image internal settings.
            
            # Method 1: img.save() (simpler if we set filepath_raw and file_format of image)
            img.filepath_raw = filepath
            img.file_format = format
            
            try:
                img.save()
                saved_paths.append(filepath)
                logger.info(f"Saved texture: {filepath}")
            except Exception as e:
                logger.error(f"Error saving texture {map_name}: {e}")
                
        # Restore
        bpy.context.scene.render.image_settings.file_format = orig_format
        
        return saved_paths
