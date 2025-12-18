import bpy
import os
import argparse
import logging
import sys
import subprocess

# Aggiungi la directory corrente al path per importare i moduli locali se necessario
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

try:
    from scene_helper import SceneHelper
    from io_helper import MeshIO
    from preprocess import MeshPreprocessor
    from remesher import GmshConverter, MmgRemesher
    from decimate import MeshDecimator
except ImportError:
    # Fallback per quando si esegue dentro Blender dove il path potrebbe essere diverso
    from .scene_helper import SceneHelper
    from .io_helper import MeshIO
    from .preprocess import MeshPreprocessor
    from .remesher import GmshConverter, MmgRemesher
    from .decimate import MeshDecimator

import shutil

# Configurazione logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("MeshOptimPipeline")

def main(input_path: str, output_path: str):
    """
    Esegue la pipeline principale di ottimizzazione mesh.
    
    1. Pulizia Scena
    2. Importazione Mesh
    3. Preprocessing (Flatten, Join, Clean, Fix)
    4. Export Temp (in /tmp)
    5. Remeshing (OBJ -> MESH -> MMGS -> MESH -> OBJ)
    6. Decimazione Finale (Target 300k facce)
    7. Export Finale
    """
    
    logger.info("=== Inizio Pipeline Mesh Optim ===")
    
    # 1. Pulisci la scena
    logger.info("Fase 1: Pulizia Scena")
    SceneHelper.cleanup_scene()
    
    # 2. Importa il modello
    logger.info(f"Fase 2: Importazione Modello da {input_path}")
    imported_objects = MeshIO.load(input_path)
    
    if not imported_objects:
        logger.error("Nessun oggetto importato. Interruzione pipeline.")
        return

    # 3. Preprocessing
    logger.info("Fase 3: Preprocessing (Flatten, Fix, Clean)")
    
    # Troviamo i veri root nella gerarchia di Blender per gli oggetti importati
    all_roots = set()
    for obj in imported_objects:
        curr = obj
        while curr.parent:
            curr = curr.parent
        all_roots.add(curr)
    roots = list(all_roots)
    
    processed_meshes = []
    
    if len(roots) == 1:
        logger.info(f"Oggetto Root identificato: {roots[0].name}")
        processed_meshes = MeshPreprocessor.process_by_material(roots[0].name)
    elif len(roots) > 1:
        logger.warning(f"Trovati {len(roots)} oggetti root: {[r.name for r in roots]}. Verranno uniti tramite un parent temporaneo.")
        dummy_root = bpy.data.objects.new("DummyRoot", None)
        bpy.context.scene.collection.objects.link(dummy_root)
        
        for r in roots:
            mat = r.matrix_world.copy()
            r.parent = dummy_root
            r.matrix_world = mat
        
        processed_meshes = MeshPreprocessor.process_by_material(dummy_root.name)
        
        if dummy_root.name in bpy.data.objects:
             bpy.data.objects.remove(dummy_root)
    else:
        logger.error("Impossibile determinare la gerarchia della mesh (Lista roots vuota).")
        return

    if not processed_meshes:
        logger.error("Preprocessing fallito (nessuna mesh finale).")
        return

    # 4. Esportazione Temporanea per Remeshing
    temp_dir = "/tmp"
    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir)

    input_filename = os.path.splitext(os.path.basename(input_path))[0]
    final_optimized_objects = []
    
    logger.info(f"Fase 4: Inizio ottimizzazione per {len(processed_meshes)} gruppi di materiale")
    
    for i, hp_mesh in enumerate(processed_meshes):
        # 4a. Setup nomi e percorsi per questo gruppo
        safe_mesh_name = hp_mesh.name.replace(" ", "_")
        base_name = f"{input_filename}_{safe_mesh_name}"
        logger.info(f"--- Processando Gruppo {i+1}/{len(processed_meshes)}: {safe_mesh_name} ---")
        
        # Esportazione temporanea HP per remeshing
        temp_dir = "/tmp"
        if not os.path.exists(temp_dir): os.makedirs(temp_dir)
        temp_hp_obj = os.path.join(temp_dir, f"{base_name}_hp.obj")
        
        if not MeshIO.export(temp_hp_obj, objects=[hp_mesh]):
            logger.error(f"Export HP fallito per {safe_mesh_name}. Salto.")
            continue

        # 5. Remeshing Pipeline (External Tools)
        logger.info(f"Fase 5 [{safe_mesh_name}]: Remeshing (Gmsh -> MMGS)")
        temp_mesh_path = GmshConverter.obj_to_mesh(temp_hp_obj, generate_3d=False)
        if not temp_mesh_path: continue
        
        optimized_mesh_path = MmgRemesher.optimize(temp_mesh_path, mode='surface')
        if not optimized_mesh_path: continue
        
        temp_remeshed_obj = GmshConverter.mesh_to_obj(optimized_mesh_path)
        if not temp_remeshed_obj: continue

        # 6. Decimazione
        logger.info(f"Fase 6 [{safe_mesh_name}]: Import e Decimazione")
        # Invece di cleanup_scene, cancelliamo solo gli oggetti remeshati precedenti se presenti
        remeshed_objects = MeshIO.load(temp_remeshed_obj)
        if not remeshed_objects: continue
        
        # Se Gmsh ha creato più pezzi, uniamoli
        lp_target = remeshed_objects[0]
        if len(remeshed_objects) > 1:
            bpy.ops.object.select_all(action='DESELECT')
            for o in remeshed_objects: o.select_set(True)
            bpy.context.view_layer.objects.active = lp_target
            bpy.ops.object.join()
        
        # Applica Decimate
        target_faces = 300000 # // len(processed_meshes) # Distribuiamo il budget di facce
        MeshDecimator.apply_decimate(lp_target, preset='CUSTOM', custom_target=target_faces, hausdorf_threshold=0.001)

        # 7. Generazione UV (PartUV)
        logger.info(f"Fase 7 [{safe_mesh_name}]: Generazione UV (PartUV)")
        temp_decimated_obj = os.path.join(temp_dir, f"{base_name}_dec.obj")
        MeshIO.export(temp_decimated_obj, objects=[lp_target])
        
        base_dir_app = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        uv_script = os.path.join(base_dir_app, "pipeline", "uv_generator.py")
        config_file = os.path.join(base_dir_app, "config", "config_partuv.yaml")
        python_exe = "/opt/partuv_env/bin/python"
        
        cmd_uv = [python_exe, uv_script, "--mesh_path", temp_decimated_obj, "--config_path", config_file, "--output_path", temp_dir, "--pack_method", "none"]
        
        try:
            res_uv = subprocess.run(cmd_uv, capture_output=True, text=True)
            if res_uv.returncode == 0:
                # 8. Import UV e Packing
                mesh_stem = f"{base_name}_dec"
                final_uv_obj_path = os.path.join(temp_dir, mesh_stem, "final_components.obj")
                
                # Rimuovi lp_target vecchio prima di caricare quello con UV
                bpy.data.objects.remove(lp_target, do_unlink=True)
                
                uv_objects = MeshIO.load(final_uv_obj_path)
                if uv_objects:
                    lp_mesh = uv_objects[0]
                    # Packing
                    try:
                        from uv_packer import UVPacker
                        UVPacker.pack_islands(lp_mesh, margin=0.001)
                    except Exception: pass
                    
                    # 9. Baking (HP -> LP)
                    logger.info(f"Fase 9 [{safe_mesh_name}]: Baking da High Poly dedicata")
                    from tex_baker import TextureAnalyzer, TextureBaker
                    
                    # Determina cartella output e sottocartella texture specifica per questa mesh
                    out_dir = os.path.dirname(output_path) if os.path.splitext(output_path)[1] else output_path
                    mesh_tex_dir = os.path.join(out_dir, f"tex_{safe_mesh_name}")
                    
                    # Analisi materiali High Poly per questo pezzo
                    mat_analysis = TextureAnalyzer.analyze_mesh_materials(hp_mesh)
                    all_maps = set()
                    for m in mat_analysis.values(): 
                        if m: all_maps.update(m['maps'].keys())
                    
                    if all_maps:
                        baker = TextureBaker(resolution=2048, margin="infinite")
                        # Esegue il bake
                        baked_imgs = baker.bake_all(hp_mesh, lp_mesh, list(all_maps))
                        
                        # Salva le immagini nella cartella specifica per la mesh
                        MeshIO.save_images_to_dir(baked_imgs, mesh_tex_dir)
                        
                        # Roughness post-process
                        if 'ROUGHNESS' not in all_maps:
                            try:
                                from roughness_gen import RoughnessGenerator
                                RoughnessGenerator.generate_roughness(mesh_tex_dir, method='AO')
                            except Exception: pass
                    
                    # 10. Assemblaggio Materiale
                    logger.info(f"Fase 10 [{safe_mesh_name}]: Assemblaggio Materiale")
                    try:
                        from material_assembler import MaterialAssembler
                        MaterialAssembler.assemble_material(lp_mesh, mesh_tex_dir)
                    except Exception as e:
                        logger.warning(f"Errore assemblaggio: {e}")
                    
                    lp_mesh.name = f"Optimized_{safe_mesh_name}"
                    final_optimized_objects.append(lp_mesh)
                    
                    # Possiamo ora nascondere la HP o rimuoverla
                    hp_mesh.hide_render = True
                    hp_mesh.hide_viewport = True
                    
        except Exception as e:
            logger.error(f"Errore critico loop optimization per {safe_mesh_name}: {e}")

    # 11. Salvataggio Finale (Combinato)
    logger.info(f"Fase 11: Salvataggio Risultato Finale Combinato")
    if final_optimized_objects:
        final_glb_path = os.path.join(output_path, f"{input_filename}_optimized.glb")
        # Nascondi tutto tranne gli optimized per l'export
        for obj in bpy.data.objects:
            if obj not in final_optimized_objects:
                obj.select_set(False)
        
        if MeshIO.export(final_glb_path, objects=final_optimized_objects):
            logger.info(f"Export GLB finale completato: {final_glb_path}")
            logger.info("=== Pipeline Completata con Successo ===")
        else:
            logger.error("Errore durante l'esportazione GLB finale.")
    else:
        logger.error("Nessun oggetto ottimizzato da esportare.")

if __name__ == "__main__":
    # Esempio di utilizzo da riga di comando (es. blender -b -P core.py -- args)
    # Per ora usiamo un parse semplice o argomenti diretti se chiamati internamente.
    # Se lanciato da CLI blender, sys.argv contiene gli argomenti di blender prima di "--"
    
    if "--" in sys.argv:
        argv = sys.argv[sys.argv.index("--") + 1:]
    else:
        argv = [] # Default o test

    parser = argparse.ArgumentParser(description="Mesh Optimization Pipeline")
    parser.add_argument("--input", type=str, required=True, help="Input mesh file path (.glb, .obj)")
    parser.add_argument("--output", type=str, required=True, help="Output mesh file path")
    
    # Se non ci sono argomenti, non crashare (utile per testing interattivo)
    if not argv:
        logger.info("Nessun argomento fornito. In attesa di chiamate dirette a main().")
    else:
        args = parser.parse_args(argv)
        main(args.input, args.output)
