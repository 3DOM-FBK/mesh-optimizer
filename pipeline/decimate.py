import bpy
import bmesh
import mathutils
from mathutils.bvhtree import BVHTree
import logging

# Configurazione logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MeshDecimator:
    """
    Classe per la decimazione di mesh usando il modificatore Decimate di Blender.
    Include logica adattiva basata sulla distanza di Hausdorff (approssimata).
    """

    PRESETS = {
        'HIGH': 200000,
        'MEDIUM': 100000,
        'LOW': 25000
    }

    @staticmethod
    def _calculate_hausdorff_one_sided(target_obj, source_obj) -> float:
        """
        Calcola la distanza di Hausdorff unilaterale (Massima distanza minima)
        dai vertici di target_obj alla superficie di source_obj.
        Utilizza un BVHTree per performance.
        """
        # Assicuriamoci che le trasformazioni siano applicate o considerate
        # Per semplicità, lavoriamo in World Space
        
        # Costruiamo il BVH tree dell'oggetto sorgente (originale)
        # Nota: serve un dependency graph per ottenere la mesh valutata corretta
        depsgraph = bpy.context.evaluated_depsgraph_get()
        source_eval = source_obj.evaluated_get(depsgraph)
        
        # Creiamo il tree dalla mesh valutata (include trasformazioni globali se configurato, 
        # ma FromObject lavora in local space solitamente. Meglio applicare le trasformazioni o gestirle).
        # Per sicurezza, trasformiamo i vertici di target_obj nello spazio locale di source_obj
        # OPPURE usiamo World Space per tutto.
        
        # Approccio World Space:
        # BVHTree.FromObject crea un tree in coordinate del mondo se applicato? No, locale.
        # Costruiamo un tree custom con coordinate World.
        
        bm = bmesh.new()
        bm.from_mesh(source_eval.data)
        bm.transform(source_obj.matrix_world) # Applica trasformazione world al bmesh temporaneo
        
        source_tree = BVHTree.FromBMesh(bm)
        bm.free()
        
        max_dist = 0.0
        
        # Itera sui vertici della mesh target (decimata)
        target_mesh = target_obj.data
        target_matrix = target_obj.matrix_world
        
        for v in target_mesh.vertices:
            world_co = target_matrix @ v.co
            # Trova il punto più vicino sulla mesh sorgente
            location, normal, index, dist = source_tree.find_nearest(world_co)
            if dist > max_dist:
                max_dist = dist
                
        return max_dist

    @staticmethod
    def apply_decimate(obj: bpy.types.Object, preset: str = 'MEDIUM', 
                       custom_target: int = None, hausdorf_threshold: float = 0.001) -> bool:
        """
        Applica il modificatore Decimate all'oggetto.
        
        Args:
            obj (bpy.types.Object): Oggetto da decimare.
            preset (str): 'HIGH', 'MEDIUM', 'LOW' o 'CUSTOM'.
            custom_target (int): Numero facce target se preset è 'CUSTOM'.
            hausdorf_threshold (float): Soglia massima di errore (Distanza Hausdorff).
            
        Returns:
            bool: True se successo, False altrimenti.
        """
        if obj.type != 'MESH':
            logger.error("L'oggetto non è una mesh.")
            return False

        # Determina il target face count
        target_faces = 0
        preset_key = preset.upper()
        
        if preset_key == 'CUSTOM':
            if custom_target is None:
                logger.error("Preset CUSTOM selezionato ma nessun custom_target fornito.")
                return False
            target_faces = custom_target
        elif preset_key in MeshDecimator.PRESETS:
            target_faces = MeshDecimator.PRESETS[preset_key]
        else:
            logger.warning(f"Preset {preset} non riconosciuto. Default a MEDIUM.")
            target_faces = MeshDecimator.PRESETS['MEDIUM']

        logger.info(f"Avvio decimazione: Preset={preset} | Target Iniziale={target_faces} | Threshold={hausdorf_threshold}")

        # Crea una copia dell'oggetto originale per riferimento (Hausdorff)
        # Assicuriamoci di scollegarla dalla collezione per non interferire, o tenerla nascosta
        original_mesh_data = obj.data.copy()
        original_obj = obj.copy()
        original_obj.data = original_mesh_data
        original_obj.name = f"{obj.name}_ORIGINAL_REF"
        # Non linkiamo original_obj alla scena per evitare clutter, lo usiamo come data block
        # Ma per il BVH tree è comodo averlo valido. Linkiamolo a una collezione nascosta se necessario.
        # O semplicemente usiamolo come "data container".
        
        # Nota: per geometry/bmesh non serve che sia in scena.
        
        initial_faces = len(obj.data.polygons)
        
        # Calcolo diagonale bounding box per soglia adattiva
        bbox_corners = [obj.matrix_world @ mathutils.Vector(corner) for corner in obj.bound_box]
        diag = (bbox_corners[6] - bbox_corners[0]).length # Corner opposti
        if diag == 0: diag = 1.0 # Evita divisioni zero su mesh puntiformi
        
        # La soglia input è intesa come frazione della diagonale (es. 0.001 = 0.1% della dimensione modello)
        adaptive_threshold = hausdorf_threshold * diag
        
        logger.info(f"Dimensioni modello (Diag): {diag:.4f}m | Soglia Hausdorff Adattiva: {adaptive_threshold:.6f} (Base: {hausdorf_threshold})")
        logger.info(f"Facce iniziali: {initial_faces}")
        
        if initial_faces <= target_faces:
            logger.info("La mesh ha già meno facce del target. Nessuna decimazione necessaria.")
            bpy.data.meshes.remove(original_mesh_data)
            return True

        # Loop adattivo (Max 6 tentativi)
        current_target = target_faces
        max_retries = 6
        success = False
        
        for i in range(max_retries):
            iteration_label = f"Iterazione {i+1}/{max_retries}"
            
            # Calcola ratio
            # Se la mesh ha subito modifiche precedenti, usiamo initial_faces "virtuale"?
            # No, il modificatore lavora sullo stato corrente.
            # Dobbiamo resettare la mesh allo stato originale ad ogni iterazione per applicare un nuovo ratio?
            # Sì, altrimenti stiamo decimando il decimato.
            
            # Ripristina la geometria originale sull'oggetto target
            obj.data = original_mesh_data.copy() # Copia fresca dai dati originali
            
            current_faces = len(obj.data.polygons)
            ratio = current_target / current_faces if current_faces > 0 else 1.0
            ratio = min(ratio, 1.0)
            
            if ratio >= 1.0:
                 logger.info(f"{iteration_label}: Target {current_target} >= Facce attuali. Skip.")
                 success = True
                 break

            # Aggiungi e applica modificatore
            mod = obj.modifiers.new(name="Decimate_Optim", type='DECIMATE')
            mod.ratio = ratio
            mod.use_collapse_triangulate = True # Aiuta a mantenere topologia pulita
            
            # Applica il modificatore
            # In Blender 4+ ops.object.modifier_apply richiede che l'oggetto sia attivo e in object mode
            bpy.context.view_layer.objects.active = obj
            bpy.ops.object.modifier_apply(modifier=mod.name)
            
            # Conta le facce ottenute
            new_face_count = len(obj.data.polygons)
            
            # Controllo Hausdorff
            # Usiamo original_obj come sorgente (High Res) e obj come target (Low Res)
            dist = MeshDecimator._calculate_hausdorff_one_sided(obj, original_obj)
            
            logger.info(f"{iteration_label}: Ratio={ratio:.4f} -> Facce={new_face_count} | Hausdorff Dist={dist:.6f} (Soglia {adaptive_threshold:.6f})")
            
            if i == max_retries - 1:
                logger.warning(f"Raggiunto limite iterazioni ({max_retries}). Accetto il risultato anche se fuori soglia.")
                success = True
                break
                
            if dist <= adaptive_threshold:
                logger.info("Ottimizzazione riuscita entro la soglia.")
                success = True
                break
            else:
                logger.info("Soglia superata. Aumento il target face count di 1.5x e riprovo.")
                current_target = int(current_target * 1.5)
        
        # Pulizia
        # Rimuovi il blocco dati originale di backup
        if original_obj:
            # original_obj è una copia python wrapper, ma i suoi dati (original_mesh_data) sono in bpy.data.meshes
            # Se non è linkato alla scena, dobbiamo rimuoverlo dai dati
            bpy.data.meshes.remove(original_mesh_data)
            # bpy.data.objects.remove(original_obj) # Se non è in scene, questo potrebbe non servire o dare errore?
            # Un oggetto non linkato viene pulito al reload, ma meglio garbage collect manuale se possibile.
            # Rimuoviamo la mesh data è sufficiente solitamente.
        
        return success
