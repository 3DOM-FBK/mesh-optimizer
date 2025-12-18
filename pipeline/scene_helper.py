import bpy
import logging

# Configurazione base del logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SceneHelper:
    """
    Classe helper per la gestione della scena di Blender.
    """

    @staticmethod
    def cleanup_scene():
        """
        Pulisce completamente la scena corrente rimuovendo:
        - Tutti gli oggetti (MESH, LIGHT, CAMERA, ecc.)
        - Tutte le collezioni (eccetto la Master Collection se non rimovibile)
        - Tutti i dati orfani (Mesh, Materiali, Texture, Luci, Camere, Curve, ecc.)
        
        L'obiettivo è ottenere uno stato 'tabula rasa'.
        """
        logger.info("Avvio pulizia completa della scena...")

        # 1. Rimuovi tutti gli oggetti dalla scena
        if bpy.context.view_layer.objects:
            bpy.ops.object.select_all(action='SELECT')
            bpy.ops.object.delete(use_global=False)
        
        # 2. Rimuovi tutte le collezioni (tranne la Scene Collection principale)
        for collection in bpy.data.collections:
            bpy.data.collections.remove(collection)

        # 3. Purge dei data-blocks orfani
        # Itera su tutte le collezioni di dati e rimuovili se non hanno utenti
        # Nota: L'ordine è importante per dipendenze (es. materiali usati da mesh)
        
        # Elimina le mesh
        for mesh in bpy.data.meshes:
            bpy.data.meshes.remove(mesh)

        # Elimina i materiali
        for mat in bpy.data.materials:
            bpy.data.materials.remove(mat)

        # Elimina le textures
        for tex in bpy.data.textures:
            bpy.data.textures.remove(tex)
            
        # Elimina le immagini
        for img in bpy.data.images:
            bpy.data.images.remove(img)

        # Elimina le luci
        for light in bpy.data.lights:
            bpy.data.lights.remove(light)

        # Elimina le camere
        for camera in bpy.data.cameras:
            bpy.data.cameras.remove(camera)
            
        # Elimina le curve
        for curve in bpy.data.curves:
            bpy.data.curves.remove(curve)

        # Un 'purge' finale tramite operatore orfani per sicurezza (più cicli per dipendenze annidate)
        for _ in range(3):
            bpy.ops.outliner.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=True)

        logger.info("Scena pulita con successo.")

    @staticmethod
    def remove_all_materials(obj: bpy.types.Object):
        """
        Rimuove tutti i materiali assegnati all'oggetto specificato e pulisce 
        le texture/immagini collegate se non più utilizzate.
        
        Args:
            obj (bpy.types.Object): L'oggetto mesh da cui rimuovere i materiali.
        """
        if obj.type != 'MESH':
            logger.warning(f"L'oggetto '{obj.name}' non è una mesh. Impossibile rimuovere materiali.")
            return

        logger.info(f"Rimozione materiali e texture associate da: {obj.name}")
        
        # Identifica i materiali unici usati da questo oggetto prima di staccarli
        used_materials = {slot.material for slot in obj.material_slots if slot.material}
        
        # Rimuovi i materiali dall'oggetto
        obj.data.materials.clear()
        
        # Pulizia mirata: Rimuovi materiali divenuti orfani e le loro immagini
        for mat in used_materials:
            # Nota: mat.users potrebbe non essere aggiornato istantaneamente senza trigger, 
            # ma dopo .clear() solitamente lo è. Se > 0 significa che è usato altrove.
            if mat.users == 0:
                # Cerca immagini nel node tree prima di rimuovere il blocco materiale
                images_to_check = set()
                if mat.use_nodes and mat.node_tree:
                    for node in mat.node_tree.nodes:
                        if node.type == 'TEX_IMAGE' and node.image:
                            images_to_check.add(node.image)
                            
                logger.info(f"Rimozione materiale orfano: {mat.name}")
                bpy.data.materials.remove(mat)
                
                # Controlla e rimuovi immagini divenute orfane
                for img in images_to_check:
                    if img.users == 0:
                        logger.info(f"Rimozione immagine orfana: {img.name}")
                        bpy.data.images.remove(img)

    @staticmethod
    def cleanup_scene_except(keep_obj: bpy.types.Object):
        """
        Pulisce la scena rimuovendo tutto ECCETTO l'oggetto specificato.
        Rimuove anche materiali e texture non utilizzati dall'oggetto salvato (tramite orphan purge).
        
        Args:
            keep_obj (bpy.types.Object): L'oggetto da preservare.
        """
        logger.info(f"Pulizia scena preservando solo: {keep_obj.name}")
        
        # 1. Rimuovi tutti gli oggetti tranne quello da mantenere
        bpy.ops.object.select_all(action='DESELECT')
        
        objs_to_remove = [o for o in bpy.context.scene.objects if o != keep_obj]
        
        if objs_to_remove:
            for o in objs_to_remove:
                o.select_set(True)
            bpy.ops.object.delete()
            
        # 2. Rimuovi collezioni vuote (opzionale, ma pulito)
        # Non rimuovere la master collection o quella dove sta l'oggetto
        # Per semplicità, spesso basta purge orphans per dati, le collection vuote non pesano.
        
        # 3. Purge Orphans per rimuovere Mesh, Materiali e Texture non più usati
        # Poiché abbiamo cancellato gli oggetti che usavano i 'vecchi' materiali, 
        # il purge li troverà come orfani (0 utenti) e li rimuoverà.
        # I materiali dell'oggetto 'keep_obj' hanno ancora 1 utente, quindi restano.
        for _ in range(3):
            bpy.ops.outliner.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=True)
            
        logger.info("Pulizia parziale completata.")

