import os
import cv2
import numpy as np
import logging

# Configurazione logging
logger = logging.getLogger(__name__)

class RoughnessGenerator:
    """
    Classe per generare una mappa Roughness partendo da mappe esistenti (Normal o AO).
    """

    @staticmethod
    def generate_roughness(tex_folder: str, method: str = 'NORMAL'):
        """
        Genera una mappa Roughness usando il metodo specificato.
        
        Args:
            tex_folder (str): Percorso della cartella contenente le texture.
            method (str): 'NORMAL' (basato su curvatura/bordi) o 'AO' (basato su occlusione/sporco).
            
        Returns:
            str: Path della mappa Roughness generata, o None se fallisce.
        """
        if method.upper() == 'NORMAL':
            return RoughnessGenerator._from_normal(tex_folder)
        elif method.upper() == 'AO':
            return RoughnessGenerator._from_ao(tex_folder)
        else:
            logger.error(f"Metodo generazione roughness '{method}' non supportato.")
            return None

    @staticmethod
    def _from_normal(tex_folder: str):
        # ... (Logica esistente normal spostata qui, con lievi adattamenti per il logging)
        # Ricerca file
        target_file = RoughnessGenerator._find_map(tex_folder, 'NORMAL')
        if not target_file: return None
        
        logger.info(f"Generating Roughness from Normal: {target_file}")
        try:
            normal_img = cv2.imread(target_file, cv2.IMREAD_COLOR)
            if normal_img is None: return None
            
            normal_f = normal_img.astype(np.float32) / 255.0
            
            # Sobel Gradients
            channel_x = normal_f[:,:,2]
            channel_y = normal_f[:,:,1]
            grad_x = cv2.Sobel(channel_x, cv2.CV_32F, 1, 0, ksize=3)
            grad_y = cv2.Sobel(channel_y, cv2.CV_32F, 0, 1, ksize=3)
            magnitude = cv2.magnitude(grad_x, grad_y)
            
            roughness_map = np.clip(magnitude * 2.0, 0, 1)
            base_roughness = 0.4
            roughness_final = base_roughness + (roughness_map * 0.6)
            roughness_final = np.clip(roughness_final, 0, 1)
            
            return RoughnessGenerator._save_map(tex_folder, target_file, roughness_final, 'ROUGHNESS')
        except Exception as e:
            logger.error(f"Error Gen Roughness from Normal: {e}")
            return None

    @staticmethod
    def _from_ao(tex_folder: str):
        # Cerca mappa AO
        target_file = RoughnessGenerator._find_map(tex_folder, 'AO') or RoughnessGenerator._find_map(tex_folder, 'AMBIENT_OCCLUSION')
        if not target_file: return None
        
        logger.info(f"Generating Roughness from AO: {target_file}")
        try:
            ao_img = cv2.imread(target_file, cv2.IMREAD_GRAYSCALE)
            if ao_img is None: return None
            
            ao_f = ao_img.astype(np.float32) / 255.0
            
            # Logica AO -> Roughness
            # AO Bassi (Neri/Cavità) -> Sporco/Polvere -> Spesso Ruvido (Roughness Alta/Bianca)
            # AO Alti (Bianchi/Esposti) -> Puliti/Usurati -> Spesso Lisci (Roughness Bassa/Nera o Media)
            
            # Invertiamo l'AO: 1.0 - ao
            # Cavita (0.0) -> Diventa 1.0 (Molto Ruvido)
            # Superficie (1.0) -> Diventa 0.0 (Molto Liscio)
            
            # Parametrizzazione
            # Possiamo mappare:
            # Cavità -> 0.9 (Ruvido)
            # Superficie -> 0.3 (Satinato base)
            
            inv_ao = 1.0 - ao_f
            roughness_final = 0.3 + (inv_ao * 0.6) # Base 0.3, Cavità arrivano a 0.9
            
            roughness_final = np.clip(roughness_final, 0, 1)
             
            return RoughnessGenerator._save_map(tex_folder, target_file, roughness_final, 'ROUGHNESS')
        except Exception as e:
            logger.error(f"Error Gen Roughness from AO: {e}")
            return None

    @staticmethod
    def _find_map(folder, keyword):
        candidates = [f for f in os.listdir(folder) if keyword in f.upper() and f.lower().endswith(('.png', '.jpg', '.tif', '.exr'))]
        if candidates: return os.path.join(folder, candidates[0])
        return None

    @staticmethod
    def _save_map(folder, source_file, data, suffix):
        roughness_save = (data * 255).astype(np.uint8)
        base_name = os.path.basename(source_file)
        
        # Replacement strategy
        upper_name = base_name.upper()
        if 'NORMAL' in upper_name:
             out_name = base_name.replace('NORMAL', suffix).replace('Normal', suffix) # Case fix
        elif 'AO' in upper_name: # Simple AO check might match chaotic names, ok for now
             out_name = base_name.replace('AO', suffix)
        elif 'AMBIENT_OCCLUSION' in upper_name:
             out_name = base_name.replace('AMBIENT_OCCLUSION', suffix)
        else:
             name_part, ext = os.path.splitext(base_name)
             out_name = f"{name_part}_{suffix}{ext}"
             
        # Fix se il replace case insensitive non ha funzionato bene o se AO è corto
        if out_name == base_name:
             name_part, ext = os.path.splitext(base_name)
             out_name = f"{name_part}_{suffix}{ext}"

        output_path = os.path.join(folder, out_name)
        cv2.imwrite(output_path, roughness_save)
        logger.info(f"Saved Roughness Map: {output_path}")
        return output_path
