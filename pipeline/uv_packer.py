import bpy
import logging

# Configurazione logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class UVPacker:
    """
    Classe per gestire il packing delle UV islands usando gli operatori di Blender.
    """

    @staticmethod
    def pack_islands(obj: bpy.types.Object, margin: float = 0.001):
        """
        Applica l'operatore 'Pack Islands' di Blender a tutte le UV dell'oggetto.
        
        Args:
            obj (bpy.types.Object): Mesh object con UV map.
            margin (float): Margine tra le isole (in spazio UV 0-1).
            
        Returns:
            bool: True se successo, False altrimenti.
        """
        if obj.type != 'MESH':
            logger.error(f"L'oggetto {obj.name} non è una mesh.")
            return False
            
        # Assicurati che l'oggetto sia attivo e selezionato
        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        
        # Passa in Edit Mode
        bpy.ops.object.mode_set(mode='EDIT')
        
        # Seleziona tutte le facce per includere tutte le UV nel packing
        bpy.ops.mesh.select_all(action='SELECT')
        
        # Seleziona tutti i vertici UV nel UV Editor (necessario per pack_islands)
        # Nota: bpy.ops.uv.select_all funziona sul contesto dell'area UV/Image Editor.
        # In modalità background potrebbe richiedere un override del contesto se non funziona direttamente.
        # Tuttavia, standard pack_islands spesso agisce sulla selezione mesh corrente se 'rotate' e altri sono true.
        
        logger.info(f"Avvio UV Packing per {obj.name} con margine {margin}...")
        
        try:
            # Esegue il packing
            # Parametri:
            # - margin: spazio tra le isole
            # - rotate: permette la rotazione per fit migliore (default True)
            bpy.ops.uv.pack_islands(margin=margin, rotate=True) # PartUV orienta già le chart? Se sì, rotate=False.
            # Se PartUV genera chart orientate a caso, meglio rotate=True.
            
            # Torna in Object Mode
            bpy.ops.object.mode_set(mode='OBJECT')
            logger.info("UV Packing completato.")
            return True
            
        except Exception as e:
            logger.error(f"Errore durante UV Packing: {e}")
            # Assicurati di uscire dall'Edit Mode anche in caso di errore
            if bpy.context.object.mode == 'EDIT':
                bpy.ops.object.mode_set(mode='OBJECT')
            return False
