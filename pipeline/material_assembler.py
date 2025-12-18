import bpy
import logging
import os

try:
    from scene_helper import SceneHelper
except ImportError:
    from .scene_helper import SceneHelper

# Configurazione logging
logger = logging.getLogger(__name__)

class MaterialAssembler:
    """
    Classe per assemblare il materiale finale sulla mesh Low Poly usando le texture bakate.
    """

    @staticmethod
    def assemble_material(low_poly_obj: bpy.types.Object, tex_dir: str):
        """
        Pulisce la scena mantenendo solo la Low Poly, rimuove i suoi materiali vecchi
        e crea un nuovo materiale PBR linkando le texture trovate nella directory.

        Args:
            low_poly_obj (bpy.types.Object): L'oggetto Low Poly.
            tex_dir (str): Directory purtroppo contenente le texture generate (Diffuse, Normal, etc.)
        """
        logger.info(f"Avvio assemblaggio materiale per: {low_poly_obj.name}")
        
        # 1. Pulizia Scena (NON FARE QUI se siamo in una pipeline multi-oggetto)
        # SceneHelper.cleanup_scene_except(low_poly_obj)
        
        # 2. Rimuovi vecchio materiale (e texture associate)
        SceneHelper.remove_all_materials(low_poly_obj)
        
        # 3. Crea nuovo materiale PBR
        mat_name = f"{low_poly_obj.name}_Mat"
        mat = bpy.data.materials.new(name=mat_name)
        mat.use_nodes = True
        low_poly_obj.data.materials.append(mat)
        
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        
        # Pulisci nodi default (tieni Output se c'è, o ricrealo)
        nodes.clear()
        
        output_node = nodes.new('ShaderNodeOutputMaterial')
        output_node.location = (400, 300)
        
        bsdf_node = nodes.new('ShaderNodeBsdfPrincipled')
        bsdf_node.location = (0, 300)
        
        links.new(bsdf_node.outputs['BSDF'], output_node.inputs['Surface'])
        
        # 4. Carica e collega le texture
        if not os.path.exists(tex_dir):
            logger.warning(f"Directory texture non trovata: {tex_dir}")
            return
            
        texture_files = [f for f in os.listdir(tex_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.tif', '.exr'))]
        
        logger.info(f"Texture trovate: {texture_files}")
        
        # Mapping base dei suffissi ai socket del Principled BSDF
        # Adattare in base ai suffissi usati dal Baker (es. _DIFFUSE, _NORMAL, _ROUGHNESS)
        # Coordinate Y per layout ordinato
        
        map_config = [
            {'patterns': ['DIFFUSE', 'ALBEDO', 'COLOR', 'BASE_COLOR'], 'socket': 'Base Color', 'non_color': False, 'y': 300},
            {'patterns': ['METALLIC', 'METALNESS'], 'socket': 'Metallic', 'non_color': True, 'y': 0},
            {'patterns': ['ROUGHNESS'], 'socket': 'Roughness', 'non_color': True, 'y': -300},
            {'patterns': ['NORMAL'], 'socket': 'Normal', 'non_color': True, 'is_normal': True, 'y': -600},
            {'patterns': ['AO', 'AMBIENT_OCCLUSION'], 'socket': None, 'non_color': True, 'is_ao': True, 'y': 600}, # AO si mixa
            {'patterns': ['EMISSION', 'EMIT'], 'socket': 'Emission Color', 'non_color': False, 'y': -900},
            # Opacity/Alpha gestion
        ]
        
        # Dizionario per tracciare cosa abbiamo caricato (per gestire AO mix dopo)
        loaded_nodes = {}
        
        for config in map_config:
            # Trova file che matcha uno dei pattern
            found_file = None
            for f in texture_files:
                for pat in config['patterns']:
                    # Controllo robusto: deve contenere il pattern
                    # Supporta: "_NORMAL.", "-Diff.", "DIFFUSE.png" (file che inizia col pattern)
                    f_upper = f.upper()
                    pat_upper = pat.upper()
                    if (f"_{pat_upper}" in f_upper or 
                        f"-{pat_upper}" in f_upper or 
                        f_upper.startswith(pat_upper) or  # File che inizia col pattern (es. DIFFUSE.png)
                        f_upper == f"{pat_upper}.PNG" or f_upper == f"{pat_upper}.JPG" or 
                        f_upper == f"{pat_upper}.JPEG" or f_upper == f"{pat_upper}.TIF" or 
                        f_upper == f"{pat_upper}.EXR"):
                        found_file = f
                        break
                if found_file: break
            
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
                    
                    # Gestione Normal Map
                    if config.get('is_normal'):
                        normal_map_node = nodes.new('ShaderNodeNormalMap')
                        normal_map_node.location = (-200, config['y'])
                        links.new(tex_node.outputs['Color'], normal_map_node.inputs['Color'])
                        links.new(normal_map_node.outputs['Normal'], bsdf_node.inputs['Normal'])
                        
                    # Gestione AO
                    elif config.get('is_ao'):
                        # Non colleghiamo nulla qui, lo gestiamo dopo nel blocco dedicato glTF
                        pass
                        
                    # Collegamento Standard
                    elif config.get('socket'):
                        # Verifica che il socket esista (compatibilità versioni blender)
                        if config['socket'] in bsdf_node.inputs:
                            links.new(tex_node.outputs['Color'], bsdf_node.inputs[config['socket']])
                            
                            # Logica specifica per Emission: strength a 1.0 se c'è texture
                            if config['socket'] == 'Emission Color' and 'Emission Strength' in bsdf_node.inputs:
                                bsdf_node.inputs['Emission Strength'].default_value = 1.0
                        else:
                            logger.warning(f"Socket '{config['socket']}' non trovato nel Principled BSDF.")
                            
                except Exception as e:
                    logger.error(f"Errore caricamento texture {found_file}: {e}")

        # Post-Processing collegamenti speciali (AO per glTF Export)
        if 'AO' in loaded_nodes: # Chiave patterns[0]
            ao_node = loaded_nodes['AO']
            
            logger.info("Configurazione AO per export glTF (Node Group speciale)...")
            
            # Crea o recupera il Node Group "gltf settings"
            group_name = "gltf settings"
            if group_name in bpy.data.node_groups:
                group = bpy.data.node_groups[group_name]
            else:
                group = bpy.data.node_groups.new(group_name, 'ShaderNodeTree')
            
            # Assicurati che il socket 'Occlusion' esista
            # Blender 4.0+ API: group.interface.new_socket
            # Blender < 4.0 API: group.inputs.new
            if not any(sock.name == 'Occlusion' for sock in group.interface.items_tree):
                 group.interface.new_socket(name='Occlusion', in_out='INPUT', socket_type='NodeSocketFloat')
            
            # Crea il nodo Gruppo nel materiale
            group_node = nodes.new('ShaderNodeGroup')
            group_node.node_tree = group
            group_node.location = (0, -100) # Sotto il Principled
            group_node.label = "gltf settings"
            
            # Collega AO -> Occlusion
            # Nota: AO Texture output è Color, Occlusion è Float. Blender fa cast automatico (media o canale R).
            links.new(ao_node.outputs['Color'], group_node.inputs['Occlusion'])
                 
        logger.info("Assemblaggio materiale completato.")
