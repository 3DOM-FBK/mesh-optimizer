import bpy
import logging
import os

try:
    from scene_helper import SceneHelper
except ImportError:
    from .scene_helper import SceneHelper

# Logging configuration
logger = logging.getLogger(__name__)

class MaterialAssembler:
    """
    Class to assemble the final material on the Low Poly mesh using baked textures.
    """

    @staticmethod
    def assemble_material(low_poly_obj: bpy.types.Object, tex_dir: str, uniform_props: dict = None):
        """
        Cleans the scene keeping only Low Poly, removes its old materials
        and creates a new PBR material linking found textures in the directory.

        Args:
            low_poly_obj (bpy.types.Object): The Low Poly object.
            tex_dir (str): Directory containing generated textures (Diffuse, Normal, etc.)
            uniform_props (dict): Optional dictionary of uniform values {'METALLIC': 0.0, ...}
        """
        logger.info(f"Starting material assembly for: {low_poly_obj.name}")
        
        if uniform_props is None:
            uniform_props = {}
            
        # 1. Scene Cleanup (DO NOT DO HERE if used in multi-object pipeline)
        # SceneHelper.cleanup_scene_except(low_poly_obj)
        
        # 2. Remove old material (and associated textures)
        SceneHelper.remove_all_materials(low_poly_obj)
        
        # 3. Create new PBR material
        mat_name = f"{low_poly_obj.name}_Mat"
        mat = bpy.data.materials.new(name=mat_name)
        mat.use_nodes = True
        low_poly_obj.data.materials.append(mat)
        
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        
        # Clean default nodes (keep Output if present, or recreate)
        nodes.clear()
        
        output_node = nodes.new('ShaderNodeOutputMaterial')
        output_node.location = (400, 300)
        
        bsdf_node = nodes.new('ShaderNodeBsdfPrincipled')
        bsdf_node.location = (0, 300)
        
        links.new(bsdf_node.outputs['BSDF'], output_node.inputs['Surface'])
        
        # 4. Load and link textures
        if not os.path.exists(tex_dir):
            logger.warning(f"Texture directory not found: {tex_dir}")
            # Even if no tex dir, we might want to apply uniforms
            # But usually tex dir exists.
            
        texture_files = []
        if os.path.exists(tex_dir):
            texture_files = [f for f in os.listdir(tex_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.tif', '.exr'))]
        
        logger.info(f"Found textures: {texture_files}")
        
        # Base mapping of suffixes to Principled BSDF sockets
        map_config = [
            {'patterns': ['DIFFUSE', 'ALBEDO', 'COLOR', 'BASE_COLOR'], 'socket': 'Base Color', 'non_color': False, 'y': 300},
            {'patterns': ['METALLIC', 'METALNESS'], 'socket': 'Metallic', 'non_color': True, 'y': 0},
            {'patterns': ['ROUGHNESS'], 'socket': 'Roughness', 'non_color': True, 'y': -300},
            {'patterns': ['NORMAL'], 'socket': 'Normal', 'non_color': True, 'is_normal': True, 'y': -600},
            {'patterns': ['AO', 'AMBIENT_OCCLUSION'], 'socket': None, 'non_color': False, 'is_ao': True, 'y': 600}, # AO is mixed
            {'patterns': ['EMISSION', 'EMIT'], 'socket': 'Emission Color', 'non_color': False, 'y': -900},
            # Opacity
        ]
        
        # Dictionary to track what we loaded (to handle AO mix later)
        loaded_nodes = {}
        
        for config in map_config:
            # 1. Try to find texture
            found_file = None
            for f in texture_files:
                for pat in config['patterns']:
                    f_upper = f.upper()
                    pat_upper = pat.upper()
                    if (f"_{pat_upper}" in f_upper or 
                        f"-{pat_upper}" in f_upper or 
                        f_upper.startswith(pat_upper) or  
                        f_upper == f"{pat_upper}.PNG" or f_upper == f"{pat_upper}.JPG" or 
                        f_upper == f"{pat_upper}.JPEG" or f_upper == f"{pat_upper}.TIF" or 
                        f_upper == f"{pat_upper}.EXR"):
                        found_file = f
                        break
                if found_file: break
            
            # 2. If texture found, load it
            if found_file:
                path = os.path.join(tex_dir, found_file)
                logger.info(f"Loading texture: {found_file} -> {config.get('socket', 'Special')}")
                
                try:
                    img = bpy.data.images.load(path)
                    
                    tex_node = nodes.new('ShaderNodeTexImage')
                    tex_node.image = img
                    tex_node.location = (-400, config['y'])
                    
                    if config['non_color']:
                        tex_node.image.colorspace_settings.name = 'Non-Color'
                        
                    loaded_nodes[config['patterns'][0]] = tex_node
                    
                    # Normal Map Handling
                    if config.get('is_normal'):
                        normal_map_node = nodes.new('ShaderNodeNormalMap')
                        normal_map_node.location = (-200, config['y'])
                        links.new(tex_node.outputs['Color'], normal_map_node.inputs['Color'])
                        links.new(normal_map_node.outputs['Normal'], bsdf_node.inputs['Normal'])
                        
                    # AO Handling
                    elif config.get('is_ao'):
                        pass
                        
                    # Standard Linking
                    elif config.get('socket'):
                        if config['socket'] in bsdf_node.inputs:
                            links.new(tex_node.outputs['Color'], bsdf_node.inputs[config['socket']])
                            
                            if config['socket'] == 'Emission Color' and 'Emission Strength' in bsdf_node.inputs:
                                bsdf_node.inputs['Emission Strength'].default_value = 1.0
                        else:
                            logger.warning(f"Socket '{config['socket']}' not found in Principled BSDF.")
                            
                except Exception as e:
                    logger.error(f"Error loading texture {found_file}: {e}")
            
            # 3. If NO texture found, check if we have a uniform value
            else:
                # Check based on pattern keys (e.g. METALLIC)
                key_found = False
                for pat in config['patterns']:
                    if pat in uniform_props:
                        # Found a uniform value!
                        val = uniform_props[pat]
                        sock_name = config.get('socket')
                        if sock_name and sock_name in bsdf_node.inputs:
                            logger.info(f"Applying uniform value for {sock_name}: {val}")
                            bsdf_node.inputs[sock_name].default_value = val
                            key_found = True
                        break

        # Post-Processing special links (AO for glTF Export)
        if 'AO' in loaded_nodes: # Key patterns[0]
            ao_node = loaded_nodes['AO']
            
            logger.info("Configuring AO for glTF export (Special Node Group)...")
            
            # Create or retrieve "gltf settings" Node Group
            group_name = "gltf settings"
            if group_name in bpy.data.node_groups:
                group = bpy.data.node_groups[group_name]
            else:
                group = bpy.data.node_groups.new(group_name, 'ShaderNodeTree')
            
            # Ensure 'Occlusion' socket exists
            # Blender 4.0+ API: group.interface.new_socket
            # Blender < 4.0 API: group.inputs.new
            if not any(sock.name == 'Occlusion' for sock in group.interface.items_tree):
                 group.interface.new_socket(name='Occlusion', in_out='INPUT', socket_type='NodeSocketFloat')
            
            # Create Group Node in material
            group_node = nodes.new('ShaderNodeGroup')
            group_node.node_tree = group
            group_node.location = (0, -100) # Below Principled
            group_node.label = "gltf settings"
            
            # Link AO -> Occlusion
            # Note: AO Texture output is Color, Occlusion is Float. Blender casts automatically (avg or R channel).
            links.new(ao_node.outputs['Color'], group_node.inputs['Occlusion'])
                 
        logger.info("Material assembly completed.")
