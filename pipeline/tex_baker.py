import bpy
import logging
import os
import numpy as np
import bmesh
from mathutils.bvhtree import BVHTree

try:
    from io_helper import MeshIO
except ImportError:
    from .io_helper import MeshIO

# Logging configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TextureAnalyzer:
    """
    Class to analyze mesh materials and identify active textures/channels
    useful for baking.
    """

    # Generic hint mapping (Node Type or Socket Name) -> PBR Channel
    # Note: We use this to infer which maps are needed
    CHANNEL_HINTS = {
        'DIFFUSE':  {'nodes': ['BSDF_DIFFUSE', 'BSDF_PRINCIPLED'], 'sockets': ['Base Color', 'Color', 'Diffuse']},
        'ROUGHNESS': {'nodes': ['BSDF_GLOSSY', 'BSDF_PRINCIPLED'], 'sockets': ['Roughness']},
        'METALLIC': {'nodes': ['BSDF_PRINCIPLED'], 'sockets': ['Metallic']},
        'NORMAL':   {'nodes': ['NORMAL_MAP', 'BUMP'], 'sockets': ['Normal']},
        'EMISSION': {'nodes': ['EMISSION', 'BSDF_PRINCIPLED'], 'sockets': ['Emission', 'Emission Color', 'Emission Strength']},
        'OPACITY':  {'nodes': ['BSDF_TRANSPARENT', 'BSDF_PRINCIPLED'], 'sockets': ['Alpha', 'Transmission', 'Transmission Weight']}
    }

    @staticmethod
    def get_material_maps(material: bpy.types.Material) -> dict:
        """
        Analyzes a material traversing the node graph to identify active PBR channels.
        Supports Principled BSDF and complex graphs (Mix Shader, etc).
        
        Args:
            material (bpy.types.Material): Material to analyze.
            
        Returns:
            dict: Dictionary of detected channels. { 'MAP_TYPE': {'inferred_from': str} }
        """
        if not material or not material.use_nodes:
            logger.warning(f"Material '{material.name if material else 'None'}' invalid or without nodes.")
            return {}

        tree = material.node_tree
        nodes = tree.nodes
        
        # Find Material Output node
        output_node = None
        for node in nodes:
            if node.type == 'OUTPUT_MATERIAL' and node.is_active_output:
                output_node = node
                break
        
        if not output_node:
            for node in nodes:
                if node.type == 'OUTPUT_MATERIAL':
                    output_node = node
                    break
        
        if not output_node:
            logger.warning(f"No OUTPUT_MATERIAL node found in '{material.name}'.")
            return {}

        # Set of detected channels
        detected_channels = {}
        
        # Traversal queue (BFS)
        queue = [output_node]
        visited = {output_node}
        
        while queue:
            curr_node = queue.pop(0)
            
            # Analyze current node
            TextureAnalyzer._analyze_node(curr_node, detected_channels)
            
            # Add nodes connected to inputs to queue
            for input_socket in curr_node.inputs:
                if input_socket.is_linked:
                    # Also check socket name for hints (e.g. "Normal")
                    TextureAnalyzer._analyze_socket(curr_node, input_socket, detected_channels)
                    
                    for link in input_socket.links:
                        from_node = link.from_node
                        if from_node not in visited:
                            visited.add(from_node)
                            queue.append(from_node)
                            
        # Force presence of NORMAL and AMBIENT_OCCLUSION because always required
        if 'NORMAL' not in detected_channels:
            detected_channels['NORMAL'] = {'source': 'Always Required'}
            
        if 'AMBIENT_OCCLUSION' not in detected_channels:
            detected_channels['AMBIENT_OCCLUSION'] = {'source': 'Always Required'}
            
        return detected_channels

    @staticmethod
    def _analyze_node(node, detected_channels):
        """Checks if node type suggests a channel."""
        node_type = node.type
        
        # Specific Logic for Principled (more accurate)
        if node_type == 'BSDF_PRINCIPLED':
            # Check specific linked inputs or non-default values
            # But here we are just marking "bake needed".
            # If Principled exists, Diffuse and Normal are almost always desired.
            if 'DIFFUSE' not in detected_channels: detected_channels['DIFFUSE'] = {'source': 'BSDF_PRINCIPLED'}
            # Check specific sockets for others
            
        # Generic Logic based on dictionary
        for channel, hints in TextureAnalyzer.CHANNEL_HINTS.items():
            if node_type in hints['nodes']:
                if channel not in detected_channels:
                    detected_channels[channel] = {'source': f"Node: {node.name} ({node_type})"}

    @staticmethod
    def _analyze_socket(node, socket, detected_channels):
        """Checks if a linked socket suggests a channel (e.g. input 'Normal')."""
        socket_name = socket.name
        
        # Normal is special: if any node has a "Normal" input linked, we need Normal Map
        if 'Normal' in socket_name and socket.is_linked:
             detected_channels['NORMAL'] = {'source': f"Socket: {socket_name} in {node.name}"}
             
        # Generic check on socket names
        for channel, hints in TextureAnalyzer.CHANNEL_HINTS.items():
            # Check if socket name matches one of hints
            if socket_name in hints['sockets'] and socket.is_linked:
                 if channel not in detected_channels:
                      detected_channels[channel] = {'source': f"Socket: {socket_name} in {node.name}"}
                      
        # Exception: Principled BSDF inputs if they have significant values even without link?
        # For now consider only if linked (texture bake).
        # If we want to capture "Fixed red color", bake is needed anyway.
        # But request is "applied maps". If not linked, it is uniform value.
        # We can decide to bake DIFFUSE always if Principled exists.
        if node.type == 'BSDF_PRINCIPLED':
             if socket_name == 'Base Color': # and not linked...
                 # If we want to bake flat colors too, enable always.
                 pass

    @staticmethod
    def analyze_mesh_materials(obj: bpy.types.Object):
        """
        Analyzes all materials assigned to the mesh.
        
        Args:
           obj (bpy.types.Object): Mesh Object.
           
        Returns:
            dict: Mapping { slot_index: { 'material_name': str, 'maps': dict } }
        """
        if obj.type != 'MESH':
            logger.error("Provided object is not a mesh.")
            return {}

        results = {}
        
        for i, slot in enumerate(obj.material_slots):
            if slot.material:
                logger.info(f"Analyzing material slot {i}: {slot.material.name}")
                maps = TextureAnalyzer.get_material_maps(slot.material)
                results[i] = {
                    'material_name': slot.material.name,
                    'maps': maps
                }
                
                # Summary log
                active_channels = list(maps.keys())
                logger.info(f"  -> Active channels found: {active_channels}")
            else:
                results[i] = None
                
        return results


class TextureBaker:
    """
    Class to handle baking textures from High Poly to Low Poly.
    """
    
    def __init__(self, resolution=2048, cage_extrusion=0.02, max_ray_distance=0.0, margin=16):
        self.resolution = resolution
        self.cage_extrusion = cage_extrusion
        self.max_ray_distance = max_ray_distance
        self.margin = margin
        
    def setup_cycles(self):
        """Configures Blender to use Cycles Baking."""
        bpy.context.scene.render.engine = 'CYCLES'
        # Setup device (try GPU, fallback CPU)
        prefs = bpy.context.preferences.addons['cycles'].preferences
        try:
            prefs.get_devices()
            cuda_devices = [d for d in prefs.devices if d.type == 'CUDA']
            if cuda_devices:
                prefs.compute_device_type = 'CUDA'
                for d in cuda_devices: d.use = True
                bpy.context.scene.cycles.device = 'GPU'
                logger.info("Cycles configured on GPU (CUDA).")
            else:
                bpy.context.scene.cycles.device = 'CPU'
                logger.info("Cycles configured on CPU.")
        except Exception:
            bpy.context.scene.cycles.device = 'CPU'
            logger.info("Error GPU config. Using CPU.")

        # Baking Optimizations
        bpy.context.scene.cycles.samples = 16 
        
    def bake_all(self, high_poly_obj, low_poly_obj, maps_list, base_output_path=None):
        """
        Executes baking for specified maps.
        """
        self.setup_cycles()
        
        # Auto calculation cage/ray distance
        logger.info("Calculating optimal distance for Baking (Cage/Ray) - BIDIRECTIONAL...")
        try:
            # Use bidirectional calculation to avoid missed rays
            suggested_dist = self.calculate_cage_distance_bidirectional(low_poly_obj, high_poly_obj)
            logger.info(f"Optimal Distance (Bidirectional) calculated: {suggested_dist:.4f}")
            
            # Set extrusion distance and ray
            self.cage_extrusion = suggested_dist
            self.max_ray_distance = suggested_dist * 2  # Double suggested distance for safety
            # In 'Selected to Active', Ray Distance is how "far" it looks. Cage Extrusion is how "inflated" low poly is to cast rays.
            
        except Exception as e:
            logger.warning(f"Optimal distance calculation failed: {e}. Using default: {self.cage_extrusion}")

        # Object Selection: Select High, then Shift-Select Low (Active)
        bpy.ops.object.select_all(action='DESELECT')
        high_poly_obj.select_set(True)
        low_poly_obj.select_set(True)
        bpy.context.view_layer.objects.active = low_poly_obj
        
        # Pre-Bake Cleanup: Clear Sharp Edges
        logger.info("Pre-bake Low Poly Cleanup: Clear Sharp Edges & Split Normals...")
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.mark_sharp(clear=True)
        bpy.ops.object.mode_set(mode='OBJECT')
        
        # Remove custom split normals if present, to avoid conflicts with smooth shading
        if low_poly_obj.data.has_custom_normals:
             low_poly_obj.data.clear_custom_split_normals_data() # Deprecated in 4.1? No, still valid < 4.2 usually.
             
        # Ensure Shade Smooth
        bpy.ops.object.shade_smooth()
        
        baked_images = {}
        
        for map_type in maps_list:
            logger.info(f"Baking map: {map_type}...")
            
            # Create target image
            img_name = f"{low_poly_obj.name}_{map_type}"
            
            if img_name in bpy.data.images:
                bpy.data.images.remove(bpy.data.images[img_name])
                
            image = bpy.data.images.new(img_name, width=self.resolution, height=self.resolution, alpha=True)
            
            self._assign_image_to_material(low_poly_obj, image)
            
            original_samples = bpy.context.scene.cycles.samples
            if map_type == 'AMBIENT_OCCLUSION':
                bpy.context.scene.cycles.samples = 64
            
            success = self._run_bake_operation(map_type)
            
            bpy.context.scene.cycles.samples = original_samples
            
            if success:
                baked_images[map_type] = image
                logger.info(f"Bake {map_type} completed.")
            else:
                logger.error(f"Bake {map_type} failed.")
                
        # If requested, save maps immediately
        if base_output_path:
            self.save_maps(baked_images, base_output_path)
            
        return baked_images

    @staticmethod
    def calculate_optimal_cage_distance(
        low_poly_obj: bpy.types.Object,
        high_poly_obj: bpy.types.Object,
        percentile: float = 95.0,
        sample_count: int = 10000,
        safety_margin: float = 1.2
    ) -> dict:
        """
        Calculate optimal cage distance for baking between low and high poly models.
        """
        # Get mesh data
        # Note: ensure objects are Mesh and have valid data
        low_matrix = low_poly_obj.matrix_world
        high_matrix = high_poly_obj.matrix_world
        
        # Build BVH tree for high poly mesh
        # We must apply transformations for correct comparison in world space
        bm_high = bmesh.new()
        bm_high.from_mesh(high_poly_obj.data)
        bm_high.transform(high_matrix)
        bvh_high = BVHTree.FromBMesh(bm_high)
        
        # Sample points from low poly mesh
        bm_low = bmesh.new()
        bm_low.from_mesh(low_poly_obj.data)
        bm_low.transform(low_matrix)
        
        vertices = [v.co for v in bm_low.verts]
        
        if len(vertices) > sample_count:
            # Random sample indices
            indices = np.random.choice(len(vertices), sample_count, replace=False)
            vertices = [vertices[i] for i in indices]
        
        distances = []
        for vert in vertices:
            location, normal, index, distance = bvh_high.find_nearest(vert)
            if location is not None:
                distances.append(distance)
        
        bm_low.free()
        bm_high.free()
        
        if not distances:
            raise ValueError("No valid distances found between meshes")
        
        distances = np.array(distances)
        min_dist = float(np.min(distances))
        max_dist = float(np.max(distances))
        mean_dist = float(np.mean(distances))
        median_dist = float(np.median(distances))
        percentile_dist = float(np.percentile(distances, percentile))
        
        suggested = percentile_dist * safety_margin
        
        return {
            'suggested_distance': suggested,
            'min_distance': min_dist,
            'max_distance': max_dist,
            'mean_distance': mean_dist,
            'median_distance': median_dist,
            'percentile_distance': percentile_dist,
            'percentile_used': percentile,
            'safety_margin': safety_margin
        }

    @staticmethod
    def calculate_cage_distance_bidirectional(
        low_poly_obj: bpy.types.Object,
        high_poly_obj: bpy.types.Object,
        percentile: float = 95.0,
        sample_count: int = 10000,
        safety_margin: float = 1.2
    ) -> float:
        """
        Calculate cage distance considering both directions (low->high and high->low).
        More accurate for complex overlapping meshes.
        
        Args:
            Same as calculate_optimal_cage_distance
        
        Returns:
            float: Combined optimal distance
        """
        
        # Calculate low -> high
        result_lh = TextureBaker.calculate_optimal_cage_distance(
            low_poly_obj, high_poly_obj, percentile, sample_count, safety_margin
        )
        
        # Calculate high -> low
        result_hl = TextureBaker.calculate_optimal_cage_distance(
            high_poly_obj, low_poly_obj, percentile, sample_count, safety_margin
        )
        
        # Take maximum to ensure both meshes are covered
        suggested = max(result_lh['suggested_distance'], result_hl['suggested_distance'])
        
        return suggested


    def save_maps(self, baked_images, base_output_path):
        """
        Saves baked maps in a 'tex' subdirectory of base path.
        
        Args:
            baked_images (dict): Output of bake_all.
            base_output_path (str): Output mesh file path (or directory).
        """
        # Determine base directory. If base_output_path is a file, get dirname.
        if os.path.splitext(base_output_path)[1]:
            output_dir = os.path.dirname(base_output_path)
        else:
            output_dir = base_output_path
            
        tex_dir = os.path.join(output_dir, "tex")
        return MeshIO.save_images_to_dir(baked_images, tex_dir)

    def _assign_image_to_material(self, obj, image):
        """Ensures that an Image Texture node with target image is active in material."""
        if not obj.material_slots:
            # Create dummy material if missing
            mat = bpy.data.materials.new(name="Bake_Dummy")
            mat.use_nodes = True
            obj.data.materials.append(mat)
        
        mat = obj.material_slots[0].material
        if not mat.use_nodes:
            mat.use_nodes = True
            
        nodes = mat.node_tree.nodes
        # Search or create Image Texture node
        tex_node = nodes.new('ShaderNodeTexImage')
        tex_node.image = image
        nodes.active = tex_node # Important: Cycles writes to active selected node
        tex_node.select = True

    def _run_bake_operation(self, map_type):
        """Executes bake operator configuring parameters."""
        try:
            bpy.context.scene.render.bake.use_selected_to_active = True
            bpy.context.scene.render.bake.cage_extrusion = self.cage_extrusion
            bpy.context.scene.render.bake.max_ray_distance = self.max_ray_distance
            
            # Infinite Margin management
            if str(self.margin).lower() == 'infinite':
                # Use resolution as margin to cover all empty space
                used_margin = self.resolution
                logger.info(f"Margin set to INFINITE (using resolution: {used_margin}px)")
            else:
                used_margin = int(self.margin)
                
            bpy.context.scene.render.bake.margin = used_margin
            
            if map_type == 'NORMAL':
                bpy.ops.object.bake(type='NORMAL')
            elif map_type == 'AMBIENT_OCCLUSION':
                bpy.ops.object.bake(type='AO')
            elif map_type == 'DIFFUSE':
                # Only Clean Color (without lights/shadows)
                # In Blender 4.x 'use_pass_color' might be different or moved.
                # For Blender 3.6/4.0 usually in bake.pass_filter / use_pass_...
                # Verify API for 4.0+. 'use_pass_color' is standard.
                bpy.context.scene.render.bake.use_pass_direct = False
                bpy.context.scene.render.bake.use_pass_indirect = False
                bpy.context.scene.render.bake.use_pass_color = True
                bpy.ops.object.bake(type='DIFFUSE')
            elif map_type == 'ROUGHNESS':
                bpy.ops.object.bake(type='ROUGHNESS')
            elif map_type == 'EMISSION':
                bpy.ops.object.bake(type='EMIT')
            elif map_type == 'OPACITY':
                 # Opacity baking requires custom setup or EMIT if routed correctly. Fallback EMIT for now?
                 # Or skip.
                 logger.warning("Bake OPACITY not fully supported standardly, skipping.")
                 return False
            else:
                logger.warning(f"Map type {map_type} not natively supported for now. Skip.")
                return False
                
            return True
        except Exception as e:
            logger.error(f"Error during bpy.ops.object.bake: {e}")
            import traceback
            traceback.print_exc()
            return False
