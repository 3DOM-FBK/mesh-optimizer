import bpy
import logging

# Configurazione logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TextureAnalyzer:
    """
    Classe per analizzare i materiali di una mesh e identificare le texture/canali attivi
    utili per il baking.
    """

    # Mapping generico di indizi (Node Type o Socket Name) -> Canale PBR
    # Nota: Usiamo questo per inferire quali mappe servono
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
        Analizza un materiale attraversando il node graph per identificare i canali PBR attivi.
        Supporta Principled BSDF e grafi complessi (Mix Shader, ecc).
        
        Args:
            material (bpy.types.Material): Il materiale da analizzare.
            
        Returns:
            dict: Dizionario dei canali attivi. { 'MAP_TYPE': {'inferred_from': str} }
        """
        if not material or not material.use_nodes:
            logger.warning(f"Materiale '{material.name if material else 'None'}' non valido o senza nodi.")
            return {}

        tree = material.node_tree
        nodes = tree.nodes
        
        # Trova il nodo Output Material
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
            logger.warning(f"Nessun nodo OUTPUT_MATERIAL trovato in '{material.name}'.")
            return {}

        # Insieme dei canali rilevati
        detected_channels = {}
        
        # Coda per attraversamento (BFS)
        queue = [output_node]
        visited = {output_node}
        
        while queue:
            curr_node = queue.pop(0)
            
            # Analizza il nodo corrente
            TextureAnalyzer._analyze_node(curr_node, detected_channels)
            
            # Aggiungi i nodi connessi agli input alla coda
            for input_socket in curr_node.inputs:
                if input_socket.is_linked:
                    # Controlliamo anche il nome del socket per indizi (es. "Normal")
                    TextureAnalyzer._analyze_socket(curr_node, input_socket, detected_channels)
                    
                    for link in input_socket.links:
                        from_node = link.from_node
                        if from_node not in visited:
                            visited.add(from_node)
                            queue.append(from_node)
                            
        # Forziamo la presenza di NORMAL e AMBIENT_OCCLUSION perché sono richieste sempre
        if 'NORMAL' not in detected_channels:
            detected_channels['NORMAL'] = {'source': 'Always Required'}
            
        if 'AMBIENT_OCCLUSION' not in detected_channels:
            detected_channels['AMBIENT_OCCLUSION'] = {'source': 'Always Required'}
            
        return detected_channels

    @staticmethod
    def _analyze_node(node, detected_channels):
        """Controlla se il tipo di nodo suggerisce un canale."""
        node_type = node.type
        
        # Logica Specifica Principled (più precisa)
        if node_type == 'BSDF_PRINCIPLED':
            # Controlla input specifici linkati o con valori non-default
            # Ma qui stiamo solo marcando "serve il bake".
            # Se c'è un Principled, Diffuse e Normal sono quasi sempre desiderati.
            if 'DIFFUSE' not in detected_channels: detected_channels['DIFFUSE'] = {'source': 'BSDF_PRINCIPLED'}
            # Controlliamo i socket specifici per gli altri
            
        # Logica Generica basata su dizionario
        for channel, hints in TextureAnalyzer.CHANNEL_HINTS.items():
            if node_type in hints['nodes']:
                if channel not in detected_channels:
                    detected_channels[channel] = {'source': f"Node: {node.name} ({node_type})"}

    @staticmethod
    def _analyze_socket(node, socket, detected_channels):
        """Controlla se un socket linkato suggerisce un canale (es. input 'Normal')."""
        socket_name = socket.name
        
        # Normal è speciale: se qualsiasi nodo ha un input "Normal" linkato, ci serve la Normal Map
        if 'Normal' in socket_name and socket.is_linked:
             detected_channels['NORMAL'] = {'source': f"Socket: {socket_name} in {node.name}"}
             
        # Controllo generico sui nomi socket
        for channel, hints in TextureAnalyzer.CHANNEL_HINTS.items():
            # Controlla se il socket name matcha uno degli indizi (case insensitive parziale?)
            if socket_name in hints['sockets'] and socket.is_linked:
                 if channel not in detected_channels:
                      detected_channels[channel] = {'source': f"Socket: {socket_name} in {node.name}"}
                      
        # Eccezione: Principled BSDF inputs se hanno valori significativi anche senza link?
        # Per ora consideriamo solo se linkati (texture bake).
        # Se vogliamo catturare "Colore rosso fisso", serve baking comunque.
        # Ma la richiesta è "mappe applicate". Se non è linkato, è un valore uniforme.
        # Possiamo decidere di bakare DIFFUSE sempre se c'è un Principled.
        if node.type == 'BSDF_PRINCIPLED':
             if socket_name == 'Base Color': # e non linkato...
                 # Se vogliamo bakare anche i colori flat, attivalo sempre.
                 pass

    @staticmethod
    def analyze_mesh_materials(obj: bpy.types.Object):
        """
        Analizza tutti i materiali assegnati alla mesh.
        
        Args:
           obj (bpy.types.Object): Oggetto mesh.
           
        Returns:
            dict: Mapping { slot_index: { 'material_name': str, 'maps': dict } }
        """
        if obj.type != 'MESH':
            logger.error("L'oggetto fornito non è una mesh.")
            return {}

        results = {}
        
        for i, slot in enumerate(obj.material_slots):
            if slot.material:
                logger.info(f"Analisi materiale slot {i}: {slot.material.name}")
                maps = TextureAnalyzer.get_material_maps(slot.material)
                results[i] = {
                    'material_name': slot.material.name,
                    'maps': maps
                }
                
                # Log di riepilogo
                active_channels = list(maps.keys())
                logger.info(f"  -> Canali attivi trovati: {active_channels}")
            else:
                results[i] = None
                
        return results


import os
import numpy as np
import bmesh
from mathutils.bvhtree import BVHTree

try:
    from io_helper import MeshIO
except ImportError:
    from .io_helper import MeshIO

class TextureBaker:
    """
    Classe per gestire il baking delle texture da High Poly a Low Poly.
    """
    
    def __init__(self, resolution=2048, cage_extrusion=0.02, max_ray_distance=0.0, margin=16):
        self.resolution = resolution
        self.cage_extrusion = cage_extrusion
        self.max_ray_distance = max_ray_distance
        self.margin = margin
        
    def setup_cycles(self):
        """Configura Blender per usare Cycles Baking."""
        bpy.context.scene.render.engine = 'CYCLES'
        # Setup device (prova GPU, fallback CPU)
        prefs = bpy.context.preferences.addons['cycles'].preferences
        try:
            prefs.get_devices()
            cuda_devices = [d for d in prefs.devices if d.type == 'CUDA']
            if cuda_devices:
                prefs.compute_device_type = 'CUDA'
                for d in cuda_devices: d.use = True
                bpy.context.scene.cycles.device = 'GPU'
                logger.info("Cycles configurato su GPU (CUDA).")
            else:
                bpy.context.scene.cycles.device = 'CPU'
                logger.info("Cycles configurato su CPU.")
        except Exception:
            bpy.context.scene.cycles.device = 'CPU'
            logger.info("Errore config GPU. Usando CPU.")

        # Ottimizzazioni Baking
        bpy.context.scene.cycles.samples = 16 
        
    def bake_all(self, high_poly_obj, low_poly_obj, maps_list, base_output_path=None):
        """
        Esegue il baking delle mappe specificate.
        """
        self.setup_cycles()
        
        # Calcolo automatico distanza cage/raggio
        logger.info("Calcolo distanza ottimale per Baking (Cage/Ray) - BIDIRECTIONAL...")
        try:
            # Usa il calcolo bidirezionale per evitare raggi mancati
            suggested_dist = self.calculate_cage_distance_bidirectional(low_poly_obj, high_poly_obj)
            logger.info(f"Distanza ottimale (Bidirezionale) calcolata: {suggested_dist:.4f}")
            
            # Imposta la distanza di estrusione e raggio
            self.cage_extrusion = suggested_dist
            self.max_ray_distance = suggested_dist * 2  # Doppia distanza suggerita per sicurezza
            # In 'Selected to Active', Ray Distance è quanto "lontano" cerca. Cage Extrusion è quanto "gonfia" la low poly per lanciare i raggi.
            
        except Exception as e:
            logger.warning(f"Calcolo distanza ottimale fallito: {e}. Uso default: {self.cage_extrusion}")

        # Selezione oggetti: Select High, then Shift-Select Low (Active)
        bpy.ops.object.select_all(action='DESELECT')
        high_poly_obj.select_set(True)
        low_poly_obj.select_set(True)
        bpy.context.view_layer.objects.active = low_poly_obj
        
        # Pre-Bake Cleanup: Clear Sharp Edges
        logger.info("Pulizia Low Poly pre-bake: Clear Sharp Edges & Split Normals...")
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.mark_sharp(clear=True)
        bpy.ops.object.mode_set(mode='OBJECT')
        
        # Rimuovi anche custom split normals se presenti, per evitare conflitti con smooth shading
        if low_poly_obj.data.has_custom_normals:
             low_poly_obj.data.clear_custom_split_normals_data() # Deprecated in 4.1? No, still valid < 4.2 usually.
             
        # Assicura Shade Smooth
        bpy.ops.object.shade_smooth()
        
        baked_images = {}
        
        for map_type in maps_list:
            logger.info(f"Baking mappa: {map_type}...")
            
            # Crea immagine target
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
                logger.info(f"Bake {map_type} completato.")
            else:
                logger.error(f"Bake {map_type} fallito.")
                
        # Se richiesto, salva subito le mappe
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
        # Nota: assicurarsi che gli oggetti siano Mesh e abbiano dati validi
        low_matrix = low_poly_obj.matrix_world
        high_matrix = high_poly_obj.matrix_world
        
        # Build BVH tree for high poly mesh
        # Dobbiamo applicare le trasformazioni per il confronto corretto nello spazio mondo
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
        Salva le mappe bakate in una sottocartella 'tex' del percorso base.
        
        Args:
            baked_images (dict): Output di bake_all.
            base_output_path (str): Percorso del file mesh output (o directory).
        """
        # Determina directory base. Se base_output_path è un file, prende la dir.
        if os.path.splitext(base_output_path)[1]:
            output_dir = os.path.dirname(base_output_path)
        else:
            output_dir = base_output_path
            
        tex_dir = os.path.join(output_dir, "tex")
        return MeshIO.save_images_to_dir(baked_images, tex_dir)

    def _assign_image_to_material(self, obj, image):
        """Assicura che un nodo Image Texture con l'immagine target sia attivo nel materiale."""
        if not obj.material_slots:
            # Crea materiale dummy se manca
            mat = bpy.data.materials.new(name="Bake_Dummy")
            mat.use_nodes = True
            obj.data.materials.append(mat)
        
        mat = obj.material_slots[0].material
        if not mat.use_nodes:
            mat.use_nodes = True
            
        nodes = mat.node_tree.nodes
        # Cerca o crea nodo Image Texture
        tex_node = nodes.new('ShaderNodeTexImage')
        tex_node.image = image
        nodes.active = tex_node # Importante: Cycles scrive sul nodo attivo selezionato
        tex_node.select = True

    def _run_bake_operation(self, map_type):
        """Esegue l'operatore bake configurando i parametri."""
        try:
            bpy.context.scene.render.bake.use_selected_to_active = True
            bpy.context.scene.render.bake.cage_extrusion = self.cage_extrusion
            bpy.context.scene.render.bake.max_ray_distance = self.max_ray_distance
            
            # Gestione margin "infinito"
            if str(self.margin).lower() == 'infinite':
                # Usa la risoluzione come margine per coprire tutto lo spazio vuoto
                used_margin = self.resolution
                logger.info(f"Margin impostato su INFINITE (utilizzando risoluzione: {used_margin}px)")
            else:
                used_margin = int(self.margin)
                
            bpy.context.scene.render.bake.margin = used_margin
            
            if map_type == 'NORMAL':
                bpy.ops.object.bake(type='NORMAL')
            elif map_type == 'AMBIENT_OCCLUSION':
                bpy.ops.object.bake(type='AO')
            elif map_type == 'DIFFUSE':
                # Solo Clean Color (senza luci/ombre)
                # In Blender 4.x 'use_pass_color' potrebbe essere diverso o spostato.
                # Per Blender 3.6/4.0 solitamente è in bake.pass_filter / use_pass_...
                # Verificare API per 4.0+. 'use_pass_color' è standard.
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
                 logger.warning("Bake OPACITY non fully supported standardly, skipping.")
                 return False
            else:
                logger.warning(f"Tipo mappa {map_type} non supportato nativamente per ora. Skip.")
                return False
                
            return True
        except Exception as e:
            logger.error(f"Errore durante bpy.ops.object.bake: {e}")
            import traceback
            traceback.print_exc()
            return False
