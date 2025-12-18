import bpy
import os
import logging
from typing import List, Optional, Union

# Configurazione base del logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MeshIO:
    """
    Classe helper per l'importazione ed esportazione di mesh (OBJ, GLB) utilizzando Blender (bpy).
    """

    @staticmethod
    def load(file_path: str) -> List[bpy.types.Object]:
        """
        Carica una mesh da file nella scena di Blender.
        Pulisce la scena prima del caricamento.
        
        Args:
            file_path (str): Il percorso assoluto del file da caricare.
            
        Returns:
            List[bpy.types.Object]: Lista degli oggetti mesh importati.
        """
        if not os.path.exists(file_path):
            logger.error(f"File non trovato: {file_path}")
            return []

        ext = os.path.splitext(file_path)[1].lower()
        try:
            if ext == '.obj':
                # Blender 4.0+ usa wm.obj_import per default (più veloce, C++)
                if hasattr(bpy.ops.wm, 'obj_import'):
                    bpy.ops.wm.obj_import(filepath=file_path)
                else:
                    # Fallback per versioni precedenti
                    bpy.ops.import_scene.obj(filepath=file_path)
                    
            elif ext in ['.glb', '.gltf']:
                bpy.ops.import_scene.gltf(filepath=file_path)
            else:
                logger.error(f"Formato non supportato: {ext}")
                return []

            # Raccogli gli oggetti importati (assumiamo siano quelli selezionati dopo l'import)
            # Nota: alcuni importer selezionano automaticamente gli oggetti.
            imported_objects = [obj for obj in bpy.context.selected_objects if obj.type == 'MESH']
            
            # Se nessun oggetto è selezionato, prova a prendere tutti i mesh nella scena
            if not imported_objects:
                imported_objects = [obj for obj in bpy.context.scene.objects if obj.type == 'MESH']

            logger.info(f"Importato {file_path} con {len(imported_objects)} oggetti mesh.")
            return imported_objects

        except Exception as e:
            logger.error(f"Errore durante l'importazione di {file_path}: {e}")
            return []

    @staticmethod
    def export(output_path: str, objects: Optional[List[bpy.types.Object]] = None) -> bool:
        """
        Esporta gli oggetti specificati (o quelli correntemente selezionati) su file.
        
        Args:
            output_path (str): Il percorso di destinazione.
            objects (List[bpy.types.Object], optional): Lista di oggetti da esportare. 
                                                        Se None, esporta la selezione corrente.
            
        Returns:
            bool: True se l'esportazione ha successo, False altrimenti.
        """
        try:
            # Crea la directory di output se non esiste
            output_dir = os.path.dirname(output_path)
            if output_dir and not os.path.exists(output_dir):
                os.makedirs(output_dir)

            # Gestione selezione
            if objects is not None:
                bpy.ops.object.select_all(action='DESELECT')
                for obj in objects:
                    obj.select_set(True)
            
            # Se ancora non c'è nulla di selezionato, seleziona tutti i mesh
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
                logger.error(f"Estensione non riconosciuta per l'export: {ext}")
                return False

            logger.info(f"Esportazione completata in: {output_path}")
            return True

        except Exception as e:
            logger.error(f"Errore durante l'esportazione in {output_path}: {e}")
            return False

    @staticmethod
    def save_images_to_dir(images_dict: dict, output_dir: str, format: str = 'PNG') -> List[str]:
        """
        Salva un dizionario di oggetti bpy.types.Image su disco.
        
        Args:
            images_dict (dict): { 'nome_mappa': bpy.types.Image }
            output_dir (str): Directory di destinazione.
            format (str): Formato file (PNG, JPEG, etc.).
            
        Returns:
            List[str]: Lista dei percorsi dei file salvati.
        """
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            
        logger.info(f"Salvataggio di {len(images_dict)} immagini in {output_dir}")
        saved_paths = []
        
        # Salva stato settings render originali per ripristinarli
        orig_format = bpy.context.scene.render.image_settings.file_format
        # orig_depth = bpy.context.scene.render.image_settings.color_depth

        bpy.context.scene.render.image_settings.file_format = format
        # Opzionale: 16 bit per mappe dati se necessario, ma png 8 bit è standard per web/GLB.
        # bpy.context.scene.render.image_settings.color_depth = '16' 

        for map_name, img in images_dict.items():
            if not img: continue
            
            # Costruisci filename
            filename = f"{map_name}.{format.lower()}"
            filepath = os.path.join(output_dir, filename)
            
            # Imposta filepath sull'immagine per save_render
            # Nota: save_render usa i settings della scena (quindi usa il path che gli diamo in filepath)
            # Ma img.save() usa img.filepath_raw e i settings interni dell'immagine.
            
            # Metodo 1: img.save() (più semplice se abbiamo impostato filepath_raw e file_format dell'immagine)
            img.filepath_raw = filepath
            img.file_format = format
            
            try:
                img.save()
                saved_paths.append(filepath)
                logger.info(f"Salvata texture: {filepath}")
            except Exception as e:
                logger.error(f"Errore salvataggio texture {map_name}: {e}")
                
        # Ripristino
        bpy.context.scene.render.image_settings.file_format = orig_format
        
        return saved_paths
