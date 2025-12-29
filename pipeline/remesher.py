import os
import subprocess
import logging
import gmsh

# Configurazione logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Path del binario CGAL remesh
CGAL_REMESH_BIN = "/opt/remesh"

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
            generate_3d (bool): Se True, tenta di generare una mesh volumetrica (tetraedri).
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
                gmsh.model.mesh.generate(3)
            
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


class CgalRemesher:
    """
    Classe wrapper per l'esecuzione del tool CGAL Adaptive Isotropic Remeshing.
    
    Utilizza il binario compilato da CGAL 6.1 che supporta:
    - Adaptive sizing field basato sulla curvatura locale
    - Protezione automatica dei bordi (mesh aperte)
    - Formati supportati: OBJ, OFF, PLY
    """
    
    @staticmethod
    def remesh(
        input_path: str,
        output_path: str = None,
        tolerance: float = 0.001,
        edge_min: float = None,
        edge_max: float = None,
        iterations: int = 5,
        cgal_bin: str = CGAL_REMESH_BIN
    ) -> str:
        """
        Esegue il remeshing adattivo usando CGAL.
        
        Args:
            input_path (str): Path del file mesh input (OBJ, OFF, PLY).
            output_path (str, optional): Path del file output. Default: *_remeshed.obj
            tolerance (float): Tolleranza di approssimazione per l'adattamento alla curvatura.
                              Valori più bassi = edge più corti nelle zone curve.
                              Default: 0.001
            edge_min (float, optional): Lunghezza minima degli edge. 
                                        Default: auto (0.1% della diagonale bbox).
            edge_max (float, optional): Lunghezza massima degli edge.
                                        Default: auto (5% della diagonale bbox).
            iterations (int): Numero di iterazioni di remeshing. Default: 5
            cgal_bin (str): Path del binario CGAL remesh. Default: /opt/remesh
            
        Returns:
            str: Path del file output se successo, None altrimenti.
        """
        if not os.path.exists(input_path):
            logger.error(f"File input non trovato: {input_path}")
            return None
        
        if not os.path.exists(cgal_bin):
            logger.error(f"Binario CGAL non trovato: {cgal_bin}")
            return None
            
        if output_path is None:
            base, ext = os.path.splitext(input_path)
            output_path = f"{base}_remeshed{ext}"
        
        # Costruisci il comando
        cmd = [cgal_bin, input_path, output_path, str(tolerance)]
        
        # Aggiungi edge_min e edge_max se specificati
        if edge_min is not None:
            cmd.append(str(edge_min))
            if edge_max is not None:
                cmd.append(str(edge_max))
                cmd.append(str(iterations))
        elif iterations != 5:
            # Se vogliamo solo cambiare le iterazioni, dobbiamo passare tutti i parametri
            # In questo caso lasciamo i default per edge_min/max
            pass
        
        logger.info(f"Esecuzione CGAL remesh: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                logger.error(f"Errore CGAL remesh (Code {result.returncode}): {result.stderr}")
                logger.error(f"CGAL Output: {result.stdout}")
                return None
            
            # Log output del tool
            if result.stdout:
                for line in result.stdout.strip().split('\n'):
                    logger.info(f"[CGAL] {line}")
            
            if os.path.exists(output_path):
                logger.info(f"Remeshing CGAL completato: {output_path}")
                return output_path
            else:
                logger.error(f"File output non creato: {output_path}")
                return None
                
        except Exception as e:
            logger.error(f"Eccezione durante esecuzione CGAL remesh: {e}")
            return None
    
    @staticmethod
    def adaptive_remesh(
        input_path: str,
        output_path: str = None,
        detail_level: str = "high",
        iterations: int = 5,
        cgal_bin: str = CGAL_REMESH_BIN
    ) -> str:
        """
        Remeshing adattivo con preset di dettaglio predefiniti.
        
        Args:
            input_path (str): Path del file mesh input.
            output_path (str, optional): Path del file output.
            detail_level (str): Livello di dettaglio:
                - "low": tolleranza alta, meno triangoli
                - "medium": bilanciato
                - "high": tolleranza bassa, più dettaglio nelle curve (default)
                - "ultra": massimo dettaglio
            iterations (int): Numero di iterazioni. Default: 5
            cgal_bin (str): Path del binario CGAL.
            
        Returns:
            str: Path del file output se successo, None altrimenti.
        """
        # Preset di tolleranza per ogni livello
        tolerance_presets = {
            "low": 0.01,
            "medium": 0.001,
            "high": 0.0005,
            "ultra": 0.0001
        }
        
        tolerance = tolerance_presets.get(detail_level, 0.001)
        
        logger.info(f"Remeshing adattivo con livello '{detail_level}' (tolerance={tolerance})")
        
        return CgalRemesher.remesh(
            input_path=input_path,
            output_path=output_path,
            tolerance=tolerance,
            iterations=iterations,
            cgal_bin=cgal_bin
        )
