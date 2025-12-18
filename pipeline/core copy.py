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
        import bpy
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
    
    logger.info(f"Fase 4: Esportazione Temporanea per {len(processed_meshes)} gruppi di materiale")
    for mesh in processed_meshes:
        # Nome riconoscibile: [nome_input]_[nome_oggetto] (es. input_Joined_MaterialName)
        # Sostituiamo eventuali spazi nel nome per sicurezza
        safe_mesh_name = mesh.name.replace(" ", "_")
        base_name = f"{input_filename}_{safe_mesh_name}"
        
        # 4a. Export OBJ
        obj_path = os.path.join(temp_dir, f"{base_name}.obj")
        if MeshIO.export(obj_path, objects=[mesh]):
            logger.info(f"Export OBJ completato: {obj_path}")
        
        # 4b. Export GLB
        glb_path = os.path.join(temp_dir, f"{base_name}.glb")
        if MeshIO.export(glb_path, objects=[mesh]):
            logger.info(f"Export GLB completato: {glb_path}")

    logger.info("Esportazione gruppi completata. Interruzione per verifica.")
    sys.exit()

    # 5. Remeshing Pipeline (External Tools)
    logger.info("Fase 5: Remeshing (Gmsh -> MMGS)")
    
    # 5a. Converti OBJ -> MESH (solo superficie per mmgs)
    temp_mesh_path = GmshConverter.obj_to_mesh(temp_obj_path, generate_3d=False)
    if not temp_mesh_path:
        logger.error("Conversione OBJ->MESH fallita.")
        return

    # 5b. Ottimizza con MMGS (Surface)
    optimized_mesh_path = MmgRemesher.optimize(temp_mesh_path, mode='surface')
    if not optimized_mesh_path:
        logger.error("Ottimizzazione MMGS fallita.")
        return

    # 5c. Converti MESH ottimizzato -> OBJ
    temp_remeshed_obj = GmshConverter.mesh_to_obj(optimized_mesh_path)
    if not temp_remeshed_obj:
         logger.error("Conversione finale MESH->OBJ fallita.")
         return

    # 6. Decimazione Finale
    logger.info("Fase 6: Decimazione Finale")
    
    # Pulizia nuovamente la scena per importare il risultato del remeshing
    SceneHelper.cleanup_scene()
    
    logger.info(f"Importazione mesh remeshata da {temp_remeshed_obj}...")
    remeshed_objects = MeshIO.load(temp_remeshed_obj)
    
    if not remeshed_objects:
        logger.error("Impossibile caricare la mesh remeshata per la decimazione.")
        return
        
    # Unione se necessario (Gmsh potrebbe esportare pezzi separati)
    final_decimate_target = remeshed_objects[0]
    if len(remeshed_objects) > 1:
         # Logica root o join diretto
         # Qui siccome sono OBJ 'piatti', probabilmente non hanno gerarchia, possiamo fare un join veloce
         # Usiamo il metodo preprocessor.flatten_and_join che ora accetta root name... scomodo se non c'è gerarchia.
         # Ma MeshIO.load ritorna oggetti.
         # Facciamo un join manuale rapido o usiamo il preprocessor adattando.
         
         # Creiamo un root fittizio al volo per riusare flatten_and_join
         import bpy
         d_root = bpy.data.objects.new("DecimRoot", None)
         bpy.context.scene.collection.objects.link(d_root)
         for o in remeshed_objects:
             o.parent = d_root
         
         final_decimate_target = MeshPreprocessor.flatten_and_join(d_root.name)
         # Clean after join needed? Maybe not strictly, but good practice.

    # Applica Decimate
    target_faces = 300000
    hausdorf = 0.001 # 0.1% della diagonale
    
    logger.info(f"Applicazione Decimator (Target: {target_faces}, Hausdorf Relativo: {hausdorf})")
    
    success_dec = MeshDecimator.apply_decimate(
        final_decimate_target, 
        preset='CUSTOM', 
        custom_target=target_faces, 
        hausdorf_threshold=hausdorf
    )
    
    if not success_dec:
        logger.warning("Decimazione completata con warning o fallita parzialmente.")
        # Proseguiamo comunque con l'export del risultato parziale

    # 7. Generazione UV (PartUV - External Process)
    logger.info("Fase 7: Generazione UV (PartUV)")
    
    # Export mesh decimata per input a PartUV
    temp_decimated_obj = os.path.join(temp_dir, f"{input_filename}_decimated.obj")
    if not MeshIO.export(temp_decimated_obj, objects=[final_decimate_target]):
        logger.error("Export mesh decimata per UV fallito.")
        return

    # Definizione path config e script
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) # /app/ o root del repo montato
    uv_script = os.path.join(base_dir, "pipeline", "uv_generator.py")
    config_file = os.path.join(base_dir, "config", "config_partuv.yaml")
    
    # Cartella output per PartUV
    # temp_dir = os.path.join(temp_dir, "uv_output")
    
    # Interprete python dedicato per PartUV (venv di sistema)
    python_exe = "/opt/partuv_env/bin/python"
    
    # Nome mesh (stem) usato da uv_generator per creare la sottocartella
    mesh_stem = f"{input_filename}_decimated"
    
    cmd_uv = [
        python_exe, uv_script,
        "--mesh_path", temp_decimated_obj,
        "--config_path", config_file,
        "--output_path", temp_dir,
        "--pack_method", "none"
        # Nota: restore_scale è attivo di default nel nuovo script, non serve flag extra.
    ]
    
    logger.info(f"Esecuzione PartUV: {' '.join(cmd_uv)}")
    
    try:
        result_uv = subprocess.run(cmd_uv, capture_output=True, text=True)
        if result_uv.returncode != 0:
            logger.error(f"Errore PartUV: {result_uv.stderr}")
            logger.error(f"PartUV Stdout: {result_uv.stdout}")
            logger.warning("PartUV fallito. Esporto la mesh decimata SENZA UV.")
            if MeshIO.export(output_path, objects=[final_decimate_target]):
                logger.info("Backup export completato.")
            return
        else:
            logger.info("PartUV completato con successo (Exit Code 0).")
            # Stampiamo stdout per debug info
            logger.info(f"PartUV Stdout: {result_uv.stdout}")
            if result_uv.stderr:
                logger.warning(f"PartUV Stderr: {result_uv.stderr}")
    except Exception as e:
        logger.error(f"Eccezione esecuzione PartUV: {e}")
        return

    # 8. UV Packing (Blender Internal) e Salvataggio Finale
    logger.info("Fase 8: Re-import, Packing e Export Finale")
    
    # Il risultato di PartUV è in final_uv_mesh
    final_uv_mesh = os.path.join(temp_dir, mesh_stem, "final_components.obj")
    
    if not os.path.exists(final_uv_mesh):
        logger.error(f"File output PartUV non trovato: {final_uv_mesh}")
        logger.warning(f"Contenuto {temp_dir}: {os.listdir(temp_dir) if os.path.exists(temp_dir) else 'Dir not found'}")
        return

    # Pulizia Scena
    SceneHelper.cleanup_scene()
    
    # Importazione risultato PartUV
    logger.info(f"Importazione mesh con UV da {final_uv_mesh}")
    uv_objects = MeshIO.load(final_uv_mesh)
    
    if not uv_objects:
        logger.error("Importazione mesh UV fallita.")
        return
        
    target_uv_obj = uv_objects[0]
    
    # Lazy import UVPacker
    try:
        from uv_packer import UVPacker
    except ImportError:
        # Fallback relative import
        try:
            from .uv_packer import UVPacker
        except ImportError:
            # Fallback direct file import if needed, assuming same dir
            import uv_packer as UVPacker
        
    logger.info("Esecuzione Pack Islands...")
    # Margine 0.001 è standard, correggi se necessario
    if UVPacker.pack_islands(target_uv_obj, margin=0.001):
        logger.info("Packing completato.")
    else:
        logger.warning("UV Packing fallito. Si procede con l'export della mesh non impaccata.")

    # Identifica la Low Poly Mesh (quella appena impaccata)
    low_poly_mesh = target_uv_obj
    low_poly_mesh.name = "LowPoly_Optimized"
    
    # 9. Analisi Materiali High Poly per Baking
    logger.info("Fase 9: Analisi Materiali High Poly per Baking")
    
    # Importiamo la mesh originale (High Poly) per analizzare il materiale
    # Non puliamo la scena per mantenere la Low Poly caricata
    logger.info(f"Importazione High Poly da {input_path}")
    high_poly_objects = MeshIO.load(input_path)
    
    if not high_poly_objects:
        logger.warning("Impossibile caricare High Poly per analisi materiali.")
    else:
        # Preprocessing High Poly: Join & Flatten
        # Necessario per avere un unico oggetto su cui fare il bake e analizzare i materiali
        logger.info("Preprocessing High Poly (Flatten & Join)...")
        
        hp_roots = set()
        for obj in high_poly_objects:
            curr = obj
            # Risaliamo la gerarchia fino a trovare una root, ma fermiamoci se incontriamo oggetti non appartenenti a questo import?
            # MeshIO.load seleziona gli oggetti importati. Di solito non hanno parent fuori dal gruppo.
            while curr.parent:
                curr = curr.parent
            hp_roots.add(curr)
        
        roots_list = list(hp_roots)
        high_poly_mesh = None
        
        if len(roots_list) == 1:
            high_poly_mesh = MeshPreprocessor.flatten_and_join(roots_list[0].name)
        elif len(roots_list) > 1:
            logger.info(f"High Poly ha {len(roots_list)} roots. Unione temporanea.")
            import bpy
            dummy_hp_root = bpy.data.objects.new("DummyHPRoot", None)
            bpy.context.scene.collection.objects.link(dummy_hp_root)
            
            for r in roots_list:
                mat = r.matrix_world.copy()
                r.parent = dummy_hp_root
                r.matrix_world = mat
                
            high_poly_mesh = MeshPreprocessor.flatten_and_join(dummy_hp_root.name)
            
            if dummy_hp_root.name in bpy.data.objects:
                bpy.data.objects.remove(dummy_hp_root)
        
        if not high_poly_mesh:
             logger.warning("Fallito il preprocessing della High Poly. Uso il primo oggetto importato come fallback.")
             high_poly_mesh = high_poly_objects[0]
        else:
             high_poly_mesh.name = "HighPoly_Source"
        
        # Lazy import TextureAnalyzer and TextureBaker
        try:
            from tex_baker import TextureAnalyzer, TextureBaker
        except ImportError:
            try:
                from .tex_baker import TextureAnalyzer, TextureBaker
            except ImportError:
                import tex_baker
                TextureAnalyzer = tex_baker.TextureAnalyzer
                TextureBaker = tex_baker.TextureBaker

        logger.info(f"Analisi dei materiali su High Poly: {high_poly_mesh.name}")
        material_analysis = TextureAnalyzer.analyze_mesh_materials(high_poly_mesh)
        
        logger.info("=== Risultato Analisi Materiali (Mappe da Bakare) ===")
        found_something_to_bake = False
        for slot_idx, mat_info in material_analysis.items():
            if mat_info:
                mat_name = mat_info['material_name']
                active_maps = list(mat_info['maps'].keys())
                logger.info(f"Slot {slot_idx} [{mat_name}]: {active_maps}")
                if active_maps:
                    found_something_to_bake = True
        
        if not found_something_to_bake:
            logger.info("Nessuna mappa attiva trovata o materiali non nodali.")
            
        # Raccogli tutti i tipi di mappa unici da tutti i materiali
        all_maps_to_bake = set()
        for mat_info in material_analysis.values():
            if mat_info and 'maps' in mat_info:
                all_maps_to_bake.update(mat_info['maps'].keys())
        
        # Converti in lista
        maps_list = list(all_maps_to_bake)
        
        if maps_list:
            logger.info(f"Avvio Baking per le mappe: {maps_list}")
            
            # Istanzia Baker
            # Resolution potrebbe essere parametrizzabile, per ora hardcoded o default
            baker = TextureBaker(resolution=2048, margin="infinite")
            
            # Esegui Bake e Salvataggio
            # Passiamo output_path come base per la cartella 'tex'
            baker.bake_all(high_poly_mesh, low_poly_mesh, maps_list, base_output_path=output_path)
            
            # --- Generazione Roughness da AO (Post-Process) ---
            if 'ROUGHNESS' not in maps_list:
                logger.info("Fase 9b: Generazione Roughness Map da AO (Post-Process)...")
                try:
                    from roughness_gen import RoughnessGenerator
                except ImportError:
                     try:
                         from .roughness_gen import RoughnessGenerator
                     except ImportError:
                         logger.warning("Modulo roughness_gen non trovato. Skip.")
                         RoughnessGenerator = None

                if RoughnessGenerator:
                    # Determina la cartella tex
                    if os.path.splitext(output_path)[1]:
                        output_dir = os.path.dirname(output_path)
                    else:
                        output_dir = output_path
                    tex_dir = os.path.join(output_dir, "tex")
                    
                    RoughnessGenerator.generate_roughness(tex_dir, method='AO')
            else:
                logger.info("Mappa ROUGHNESS già presente in lista bake. Salto generazione procedurale.")
            
        else:
            logger.warning("Nessuna mappa da bakare identificata.")
    
    # 10. Assemblaggio Materiale PBR Finale
    logger.info("Fase 10: Assemblaggio Materiale PBR su Low Poly")
    
    # Determina tex_dir ancora una volta per sicurezza (anche se non generata roughness)
    if os.path.splitext(output_path)[1]:
        output_dir = os.path.dirname(output_path)
    else:
        output_dir = output_path
    tex_dir = os.path.join(output_dir, "tex")
    
    try:
        from material_assembler import MaterialAssembler
    except ImportError:
        try:
            from .material_assembler import MaterialAssembler
        except ImportError:
            logger.warning("Modulo material_assembler non trovato. Skip assembly.")
            MaterialAssembler = None

    if MaterialAssembler and os.path.exists(tex_dir):
        MaterialAssembler.assemble_material(low_poly_mesh, tex_dir)
    else:
        logger.warning("Assemblaggio saltato (Modulo mancante o cartella texture vuota).")

    # 11. Salvataggio Finale (GLB e OBJ)
    logger.info(f"Fase 11: Salvataggio risultato finale")
    
    # Export GLB (Geometry + Embedded Textures/Material)
    final_glb_path = os.path.join(output_path, f"{input_filename}.glb")
    if MeshIO.export(final_glb_path, objects=[low_poly_mesh]):
        logger.info(f"Export GLB completato: {final_glb_path}")
        logger.info("=== Pipeline Completata con Successo ===")
    else:
        logger.error("Errore durante l'esportazione GLB.")

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
