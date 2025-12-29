import bpy
import bmesh
import mathutils
from mathutils.bvhtree import BVHTree
import logging

# Logging configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MeshDecimator:
    """
    Class for mesh decimation using Blender's Decimate modifier.
    Includes adaptive logic based on Hausdorff distance (approximated).
    """

    PRESETS = {
        'HIGH': 200000,
        'MEDIUM': 100000,
        'LOW': 25000
    }

    @staticmethod
    def _calculate_hausdorff_one_sided(target_obj, source_obj) -> float:
        """
        Calculates one-sided Hausdorff distance (Maximum minimum distance)
        from vertices of target_obj to the surface of source_obj.
        Uses a BVHTree for performance.
        """
        # Ensure transformations are applied or considered
        # For simplicity, we work in World Space
        
        # Build BVH tree of source object (original)
        # Note: a dependency graph is needed to get the correct evaluated mesh
        depsgraph = bpy.context.evaluated_depsgraph_get()
        source_eval = source_obj.evaluated_get(depsgraph)
        
        # Create tree from evaluated mesh (includes global transformations if configured,
        # but FromObject usually works in local space. Better to apply transforms or handle them).
        # To be safe, we transform target_obj vertices to source_obj local space
        # OR use World Space for everything.
        
        # World Space approach:
        # BVHTree.FromObject creates a tree in world coords if applied? No, local.
        # We build a custom tree with World coordinates.
        
        bm = bmesh.new()
        bm.from_mesh(source_eval.data)
        bm.transform(source_obj.matrix_world) # Apply world transform to temporary bmesh
        
        source_tree = BVHTree.FromBMesh(bm)
        bm.free()
        
        max_dist = 0.0
        
        # Iterate over target mesh vertices (decimated)
        target_mesh = target_obj.data
        target_matrix = target_obj.matrix_world
        
        for v in target_mesh.vertices:
            world_co = target_matrix @ v.co
            # Find nearest point on source mesh
            location, normal, index, dist = source_tree.find_nearest(world_co)
            if dist > max_dist:
                max_dist = dist
                
        return max_dist

    @staticmethod
    def apply_decimate(obj: bpy.types.Object, preset: str = 'MEDIUM', 
                       custom_target: int = None, hausdorf_threshold: float = 0.001) -> bool:
        """
        Applies the Decimate modifier to the object.
        
        Args:
            obj (bpy.types.Object): Object to decimate.
            preset (str): 'HIGH', 'MEDIUM', 'LOW' or 'CUSTOM'.
            custom_target (int): Target face count if preset is 'CUSTOM'.
            hausdorf_threshold (float): Maximum error threshold (Hausdorff distance).
            
        Returns:
            bool: True if successful, False otherwise.
        """
        if obj.type != 'MESH':
            logger.error("Object is not a mesh.")
            return False

        # Determine target face count
        target_faces = 0
        preset_key = preset.upper()
        
        if preset_key == 'CUSTOM':
            if custom_target is None:
                logger.error("CUSTOM preset selected but no custom_target provided.")
                return False
            target_faces = custom_target
        elif preset_key in MeshDecimator.PRESETS:
            target_faces = MeshDecimator.PRESETS[preset_key]
        else:
            logger.warning(f"Preset {preset} not recognized. Defaulting to MEDIUM.")
            target_faces = MeshDecimator.PRESETS['MEDIUM']

        logger.info(f"Starting decimation: Preset={preset} | Initial Target={target_faces} | Threshold={hausdorf_threshold}")

        # Create a copy of the original object for reference (Hausdorff)
        # Ensure to unlink it from collection to not interfere, or keep it hidden
        original_mesh_data = obj.data.copy()
        original_obj = obj.copy()
        original_obj.data = original_mesh_data
        original_obj.name = f"{obj.name}_ORIGINAL_REF"
        # We don't link original_obj to scene to avoid clutter, we use it as data block
        # But for BVH tree it is convenient to have it valid. Link it to a hidden collection if necessary.
        # Or just use it as "data container".
        
        # Note: for geometry/bmesh it doesn't need to be in scene.
        
        initial_faces = len(obj.data.polygons)
        
        # Calculate bounding box diagonal for adaptive threshold
        bbox_corners = [obj.matrix_world @ mathutils.Vector(corner) for corner in obj.bound_box]
        diag = (bbox_corners[6] - bbox_corners[0]).length # Opposite corners
        if diag == 0: diag = 1.0 # Avoid division by zero on point meshes
        
        # Input threshold is intended as fraction of diagonal (e.g. 0.001 = 0.1% of model size)
        adaptive_threshold = hausdorf_threshold * diag
        
        logger.info(f"Model Dimensions (Diag): {diag:.4f}m | Adaptive Hausdorff Threshold: {adaptive_threshold:.6f} (Base: {hausdorf_threshold})")
        logger.info(f"Initial faces: {initial_faces}")
        
        if initial_faces <= target_faces:
            logger.info("Mesh already has fewer faces than target. No decimation needed.")
            bpy.data.meshes.remove(original_mesh_data)
            return True

        # Adaptive Loop (Max 6 tries)
        current_target = target_faces
        max_retries = 6
        success = False
        
        for i in range(max_retries):
            iteration_label = f"Iteration {i+1}/{max_retries}"
            
            # Calculate ratio
            # Must reset mesh to original state at each iteration to apply new ratio?
            # Yes, otherwise we are decimating the decimated.
            
            # Restore original geometry on target object
            obj.data = original_mesh_data.copy() # Fresh copy from original data
            
            current_faces = len(obj.data.polygons)
            ratio = current_target / current_faces if current_faces > 0 else 1.0
            ratio = min(ratio, 1.0)
            
            if ratio >= 1.0:
                 logger.info(f"{iteration_label}: Target {current_target} >= Current faces. Skip.")
                 success = True
                 break

            # Add and apply modifier
            mod = obj.modifiers.new(name="Decimate_Optim", type='DECIMATE')
            mod.ratio = ratio
            mod.use_collapse_triangulate = True # Helps keeping clean topology
            
            # Apply modifier
            # In Blender 4+ ops.object.modifier_apply requires object to be active and in object mode
            bpy.context.view_layer.objects.active = obj
            bpy.ops.object.modifier_apply(modifier=mod.name)
            
            # Count obtained faces
            new_face_count = len(obj.data.polygons)
            
            # Hausdorff Check
            # Use original_obj as source (High Res) and obj as target (Low Res)
            dist = MeshDecimator._calculate_hausdorff_one_sided(obj, original_obj)
            
            logger.info(f"{iteration_label}: Ratio={ratio:.4f} -> Faces={new_face_count} | Hausdorff Dist={dist:.6f} (Threshold {adaptive_threshold:.6f})")
            
            if i == max_retries - 1:
                logger.warning(f"Reached iteration limit ({max_retries}). Accepting result even if out of threshold.")
                success = True
                break
                
            if dist <= adaptive_threshold:
                logger.info("Optimization successful within threshold.")
                success = True
                break
            else:
                logger.info("Threshold exceeded. Increasing target face count by 1.5x and retrying.")
                current_target = int(current_target * 1.5)
        
        # Cleanup
        # Remove original backup data block
        if original_obj:
            # original_obj is a python wrapper copy, but its data (original_mesh_data) are in bpy.data.meshes
            # If not linked to scene, we must remove it from data
            bpy.data.meshes.remove(original_mesh_data)
            # bpy.data.objects.remove(original_obj) # If not in scene, this might not be needed or error?
            # Unlinked object is cleaned on reload, but garbage collect manual is better if possible.
            # Removing mesh data is usually sufficient.
        
        return success
