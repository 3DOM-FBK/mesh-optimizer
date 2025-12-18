import os
import subprocess
import logging
import gmsh

# Configurazione logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class GmshConverter:
    """
    Classe per la conversione di formati mesh usando Gmsh.
    """
    @staticmethod
    def obj_to_mesh(obj_path: str, output_path: str = None, generate_3d: bool = False) -> str:
        """
        Converte un file OBJ in formato MEDIT (.mesh).
        
        Args:
            obj_path (str): Path del file OBJ input.
            output_path (str, optional): Path output. Se None, usa lo stesso nome con estensione .mesh.
            generate_3d (bool): Se True, tenta di generare una mesh volumetrica (tetraedri)
                                prima di salvare. Utile per mmg3d.
        """
        if not os.path.exists(obj_path):
            logger.error(f"File input non trovato: {obj_path}")
            return None
            
        if output_path is None:
            output_path = os.path.splitext(obj_path)[0] + ".mesh"
            
        try:
            if not gmsh.isInitialized():
                gmsh.initialize()
            
            gmsh.clear()
            # Merge carica il file nella scena corrente di Gmsh
            gmsh.merge(obj_path)
            
            if generate_3d:
                logger.info("Tentativo di generazione mesh volumetrica (3D)...")
                # Crea un Surface Loop e un Volume dai surface caricati?
                # Gmsh a volte lo fa automaticamente se la superficie è chiusa con `generate(3)`.
                # Se è un semplice OBJ, è solo un insieme di triangoli.
                gmsh.model.mesh.generate(3)
            
            # Imposta la versione del formato Msh (anche se .mesh è diverso, aiuta internamente)
            # Salva in formato .mesh
            gmsh.write(output_path)
            logger.info(f"Conversione OBJ -> MESH completata: {output_path}")
            
            return output_path
        except Exception as e:
            logger.error(f"Errore conversione OBJ -> MESH: {e}")
            return None

    @staticmethod
    def mesh_to_obj(mesh_path: str, output_path: str = None) -> str:
        """
        Converte un file .mesh in OBJ.
        """
        if not os.path.exists(mesh_path):
            logger.error(f"File input non trovato: {mesh_path}")
            return None

        if output_path is None:
            output_path = os.path.splitext(mesh_path)[0] + ".obj"

        try:
            if not gmsh.isInitialized():
                gmsh.initialize()
            
            gmsh.clear()
            gmsh.merge(mesh_path)
            gmsh.write(output_path)
            logger.info(f"Conversione MESH -> OBJ completata: {output_path}")
            return output_path
        except Exception as e:
             logger.error(f"Errore conversione MESH -> OBJ: {e}")
             return None

class MmgRemesher:
    """
    Classe wrapper per l'esecuzione di MMG3D.
    """
    @staticmethod
    def optimize(mesh_path: str, output_path: str = None, mode: str = 'surface', options: list = None) -> str:
        """
        Esegue l'ottimizzazione MMG sul file specificato.
        
        Args:
            mesh_path (str): Input .mesh file.
            output_path (str, optional): Output .mesh file. Defaults to *_optim.mesh.
            mode (str): 'surface' per mmgs_O3, 'volume' per mmg3d_O3.
            options (list, optional): Opzioni aggiuntive.
        """
        if not os.path.exists(mesh_path):
            logger.error(f"File mesh non trovato: {mesh_path}")
            return None
            
        if output_path is None:
            base, ext = os.path.splitext(mesh_path)
            output_path = f"{base}_optim{ext}"
            
        # Selezione tool
        if mode == 'volume':
            tool = "mmg3d_O3"
        else:
            tool = "mmgs_O3"
            # tool = "mmg3d_O3"
            
        cmd = [tool, "-in", mesh_path, "-out", output_path, "-hausd", "0.005", "-optim", "-noinsert", "-nomove", "-noswap"]
        
        if options:
            cmd.extend(options)
        
        logger.info(f"Esecuzione {tool}: {' '.join(cmd)}")
        try:
            # Esegue il comando. Check=True solleva eccezione se fallisce.
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                logger.error(f"Errore {tool} (Code {result.returncode}): {result.stderr}")
                logger.error(f"{tool} Output: {result.stdout}")
                return None
                
            logger.info(f"Ottimizzazione {tool} completata: {output_path}")
            return output_path
        except Exception as e:
            logger.error(f"Eccezione durante esecuzione {tool}: {e}")
            return None
