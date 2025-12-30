import bpy
import os
import argparse
import logging
import sys
import subprocess
import shutil
import urllib.request

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("MeshOptimPipeline")

# Add current directory to path to import local modules
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

try:
    from scene_helper import SceneHelper
    from io_helper import MeshIO
    from preprocess import MeshPreprocessor
    from remesher import CgalRemesher
    from decimate import MeshDecimator
    # Modules imported on-demand or here if preferred
except ImportError:
    # Fallback for internal package execution
    from .scene_helper import SceneHelper
    from .io_helper import MeshIO
    from .preprocess import MeshPreprocessor
    from .remesher import CgalRemesher
    from .decimate import MeshDecimator

def ensure_checkpoint_exists(base_dir: str):
    """
    Checks if 'model_objaverse.ckpt' exists in the script folder.
    If not, downloads it from HuggingFace.
    """
    filename = "model_objaverse.ckpt"
    ckpt_path = os.path.join(base_dir, filename)
    
    if os.path.exists(ckpt_path):
        logger.info(f"Checkpoint present: {ckpt_path}")
        return ckpt_path
        
    url = "https://huggingface.co/mikaelaangel/partfield-ckpt/resolve/main/model_objaverse.ckpt"
    logger.info(f"Checkpoint missing. Starting download from: {url}")
    
    try:
        # User-Agent to reduce blocking risk
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        )
        with urllib.request.urlopen(req) as response, open(ckpt_path, 'wb') as out_file:
            shutil.copyfileobj(response, out_file)
        logger.info("Checkpoint download completed.")
    except Exception as e:
        raise RuntimeError(f"Unable to download checkpoint: {e}")
        
    return ckpt_path

def main(input_path: str, output_path: str, decimation_presets: str = "MEDIUM", image_resolution: int = 2048,
         remesh_tolerance=None, remesh_edge_min=None, remesh_edge_max=None, remesh_iterations=None,
         final_hausdorff=None):
    """
    Robust mesh optimization pipeline.
    Interrupts execution in case of critical error at any stage.
    """
    logger.info("=== Start Mesh Optim Pipeline (Robust Mode) ===")
    
    try:
        # Pre-Checks
        if not os.path.exists(input_path):
            raise FileNotFoundError(f"Input file not found: {input_path}")
            
        script_dir = os.path.dirname(os.path.abspath(__file__))
        
        # 1. Scene Cleanup
        logger.info("Phase 1: Scene Cleanup")
        SceneHelper.cleanup_scene()
        
        # 2. Import
        logger.info(f"Phase 2: Import {input_path}")
        imported_objects = MeshIO.load(input_path)
        if not imported_objects:
            raise RuntimeError("No objects imported.")
            
        # 3. Preprocessing
        logger.info("Phase 3: Preprocessing")
        all_roots = set()
        for obj in imported_objects:
            curr = obj
            while curr.parent: curr = curr.parent
            all_roots.add(curr)
        roots = list(all_roots)
        
        processed_meshes = []
        if len(roots) == 1:
            processed_meshes = MeshPreprocessor.process_by_material(roots[0].name)
        elif len(roots) > 1:
            dummy = bpy.data.objects.new("DummyRoot", None)
            bpy.context.scene.collection.objects.link(dummy)
            for r in roots:
                r.parent = dummy
            processed_meshes = MeshPreprocessor.process_by_material(dummy.name)
            bpy.data.objects.remove(dummy)
        else:
            raise RuntimeError("Unable to determine mesh hierarchy.")
            
        if not processed_meshes:
            raise RuntimeError("Preprocessing failed: no resulting meshes.")

        # Checkpoint Download (Before Pipeline Loop / Before UV)
        logger.info("Verifying ML Model Checkpoint...")
        # Save in the project root (one lever up from pipeline dir) where main.py is
        project_root = os.path.dirname(script_dir)
        ensure_checkpoint_exists(project_root)

        # Setup Temp
        import uuid
        base_temp_dir = "/tmp"
        temp_dir = os.path.join(base_temp_dir, f"optim_{uuid.uuid4().hex}")
        if not os.path.exists(temp_dir): os.makedirs(temp_dir)
        logger.info(f"Using temp directory: {temp_dir}")
        
        input_filename = os.path.splitext(os.path.basename(input_path))[0]
        final_optimized_objects = []
        
        # 4. Optimization Loop
        logger.info(f"Starting optimization for {len(processed_meshes)} meshes...")
        
        for i, hp_mesh in enumerate(processed_meshes):
            safe_name = hp_mesh.name.replace(" ", "_")
            logger.info(f"--- Processing Mesh {i+1}/{len(processed_meshes)}: {safe_name} ---")
            
            base_name = f"{input_filename}_{safe_name}"
            
            # Export HP Temp
            temp_hp = os.path.join(temp_dir, f"{base_name}_hp.obj")
            if not MeshIO.export(temp_hp, objects=[hp_mesh]):
                raise RuntimeError(f"Export HP failed for {safe_name}")
            
            # 5. Remeshing
            logger.info(f"Phase 5 [{safe_name}]: CGAL Remeshing")
            temp_remeshed = os.path.join(temp_dir, f"{base_name}_remeshed.obj")
            
            # Parametri Remesh: Use passed args or defaults (calculated or preset)
            # Default tolerance if not specified is 0.001
            r_tol = remesh_tolerance if remesh_tolerance is not None else 0.001
            
            # Default iterations if not specified is 5
            r_iter = int(remesh_iterations) if remesh_iterations is not None else 5
            
            r_min = remesh_edge_min
            r_max = remesh_edge_max
            
            # Se edge_min/max non sono specificati MA vogliamo invocare il remesher con parametri specifici
            # (es. se vogliamo custom iter o tolerance), calcoliamo i default AUTO qui in Python
            # per passarli esplicitamente.
            # Questo serve perch il wrapper/binario richiede tutti i parametri se se ne passano alcuni avanzati.
            
            if r_min is None or r_max is None:
                # Calcolo BBox Diagonal per Auto-Values
                bbox = hp_mesh.dimensions
                import math
                diag = math.sqrt(bbox.x**2 + bbox.y**2 + bbox.z**2)
                
                if r_min is None: r_min = diag * 0.001  # 0.1%
                if r_max is None: r_max = diag * 0.05   # 5%
            
            # logger.info(f"Remesh Params: Tol={r_tol}, Min={r_min}, Max={r_max}, Iter={r_iter}")
            
            # Use raw remesh instead of adaptive_remesh to control specific params
            remeshed_path = CgalRemesher.remesh(
                temp_hp, 
                temp_remeshed, 
                tolerance=r_tol, 
                edge_min=r_min, 
                edge_max=r_max, 
                iterations=r_iter
            )
            
            if not remeshed_path:
                raise RuntimeError(f"Remeshing failed for {safe_name}")
                
            # 6. Initial Decimation
            logger.info(f"Phase 6 [{safe_name}]: Decimation Target 300k")
            remeshed_objs = MeshIO.load(remeshed_path)
            if not remeshed_objs:
                raise RuntimeError(f"Load remeshed obj failed for {safe_name}")
            
            lp_target = remeshed_objs[0]
            if len(remeshed_objs) > 1:
                bpy.ops.object.select_all(action='DESELECT')
                for o in remeshed_objs: o.select_set(True)
                bpy.context.view_layer.objects.active = lp_target
                bpy.ops.object.join()
                
            if not MeshDecimator.apply_decimate(lp_target, preset='CUSTOM', custom_target=300000, hausdorf_threshold=0.001):
                raise RuntimeError(f"Initial decimation failed for {safe_name}")
            
            # 7. UV Generation (PartUV)
            logger.info(f"Phase 7 [{safe_name}]: PartUV Generation")
            temp_dec = os.path.join(temp_dir, f"{base_name}_dec.obj")
            MeshIO.export(temp_dec, objects=[lp_target])
            
            uv_script = os.path.join(script_dir, "uv_generator.py")
            config_file = os.path.join(os.path.dirname(script_dir), "config", "config_partuv.yaml")
            python_exe = "/opt/partuv_env/bin/python" # Specific PartUV Environment
            
            cmd_uv = [
                python_exe, uv_script, 
                "--mesh_path", temp_dec, 
                "--config_path", config_file, 
                "--output_path", temp_dir, 
                "--pack_method", "none"
            ]
            
            proc = subprocess.run(cmd_uv, capture_output=True, text=True)
            if proc.returncode != 0:
                logger.error(f"PartUV Error Output:\n{proc.stderr}")
                raise RuntimeError(f"PartUV generation failed for {safe_name}")
            
            # 8. Load UV & Packing
            logger.info(f"Phase 8 [{safe_name}]: Import UV & Pack")
            uv_obj_path = os.path.join(temp_dir, f"{base_name}_dec", "final_components.obj")
            
            bpy.data.objects.remove(lp_target, do_unlink=True)
            uv_objects = MeshIO.load(uv_obj_path)
            if not uv_objects:
                raise RuntimeError(f"UV mesh load failed for {safe_name}")
            lp_mesh = uv_objects[0]
            
            try:
                from uv_packer import UVPacker
                UVPacker.pack_islands(lp_mesh, margin=0.001)
            except Exception as e:
                logger.warning(f"UV Packing warning: {e}. Proceeding anyway.")
                
            # 9. Baking
            logger.info(f"Phase 9 [{safe_name}]: Baking Maps")
            try:
                from tex_baker import TextureAnalyzer, TextureBaker
                out_dir = os.path.dirname(output_path) if os.path.splitext(output_path)[1] else output_path
                mesh_tex_dir = os.path.join(out_dir, f"tex_{safe_name}")
                
                mat_analysis = TextureAnalyzer.analyze_mesh_materials(hp_mesh)
                all_maps = set()
                for m in mat_analysis.values(): 
                    if m: all_maps.update(m['maps'].keys())
                
                if all_maps:
                    # Use passed image_resolution
                    baker = TextureBaker(resolution=image_resolution, margin="infinite")
                    baked = baker.bake_all(hp_mesh, lp_mesh, list(all_maps))
                    MeshIO.save_images_to_dir(baked, mesh_tex_dir)
                    
                    if 'ROUGHNESS' not in all_maps:
                        from roughness_gen import RoughnessGenerator
                        RoughnessGenerator.generate_roughness(mesh_tex_dir, method='AO')
            except Exception as e:
                raise RuntimeError(f"Baking failed for {safe_name}: {e}")

            # 10. Assemble
            logger.info(f"Phase 10 [{safe_name}]: Assemble Materials")
            try:
                from material_assembler import MaterialAssembler
                MaterialAssembler.assemble_material(lp_mesh, mesh_tex_dir)
            except Exception as e:
                raise RuntimeError(f"Material Assembly failed for {safe_name}: {e}")
                
            # 11. Final Decimation
            logger.info(f"Phase 11 [{safe_name}]: Final Decimation (Preset: {decimation_presets})")
            
            # Use provided hausdorff or default 0.001
            h_thresh = final_hausdorff if final_hausdorff is not None else 0.001
            
            if not MeshDecimator.apply_decimate(lp_mesh, preset=decimation_presets, custom_target=300000, hausdorf_threshold=h_thresh):
                raise RuntimeError(f"Final decimation failed for {safe_name} (Preset: {decimation_presets})")
            
            lp_mesh.name = f"Optimized_{safe_name}"
            final_optimized_objects.append(lp_mesh)
            
            # Hide High Poly
            hp_mesh.hide_render = True
            hp_mesh.hide_viewport = True
            
        # 12. Final Export
        logger.info("Phase 12: Final GLB Export")
        if final_optimized_objects:
            final_glb_path = os.path.join(output_path, f"{input_filename}_optimized.glb")
            
            bpy.ops.object.select_all(action='DESELECT')
            for obj in final_optimized_objects:
                obj.select_set(True)
                
            if MeshIO.export(final_glb_path, objects=final_optimized_objects):
                logger.info(f"=== Pipeline Completed. Output: {final_glb_path} ===")
            else:
                raise RuntimeError("Final GLB Export failed.")
        else:
            raise RuntimeError("No final optimized objects produced.")

    except Exception as e:
        logger.error(f"CRITICAL ERROR: {e}")
        # Terminate process with error code to signal failure
        sys.exit(1)
    finally:
        # Cleanup ALL temporary data
        if 'temp_dir' in locals() and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
                logger.info(f"Cleaned up temporary directory: {temp_dir}")
            except Exception as e:
                logger.warning(f"Failed to cleanup temp directory {temp_dir}: {e}")

if __name__ == "__main__":
    if "--" in sys.argv:
        argv = sys.argv[sys.argv.index("--") + 1:]
    else:
        argv = []

    parser = argparse.ArgumentParser(description="Mesh Optimization Pipeline")
    parser.add_argument("--input", type=str, required=True, help="Input mesh file")
    parser.add_argument("--output", type=str, required=True, help="Output mesh file")
    parser.add_argument("--decimation_presets", type=str, default="MEDIUM", help="Decimation Preset (LOW, MEDIUM, HIGH, CUSTOM)")
    parser.add_argument("--image_resolution", type=int, default=2048, help="Image resolution")
    
    # Remesh arguments
    parser.add_argument("--remesh_tolerance", type=float, default=None, help="Remesh tolerance")
    parser.add_argument("--remesh_edge_min", type=float, default=None, help="Remesh edge min")
    parser.add_argument("--remesh_edge_max", type=float, default=None, help="Remesh edge max")
    parser.add_argument("--remesh_iterations", type=int, default=None, help="Remesh iterations")
    
    # Decimation arguments
    parser.add_argument("--final_hausdorff", type=float, default=None, help="Final decimation Hausdorff threshold")
    
    args = parser.parse_args(argv)
    
    # Create output directory based on input filename
    input_filename = os.path.splitext(os.path.basename(args.input))[0]
    output_dir = os.path.join(args.output, input_filename)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    main(args.input, output_dir, args.decimation_presets, args.image_resolution,
         remesh_tolerance=args.remesh_tolerance,
         remesh_edge_min=args.remesh_edge_min,
         remesh_edge_max=args.remesh_edge_max,
         remesh_iterations=args.remesh_iterations,
         final_hausdorff=args.final_hausdorff)
