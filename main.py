import argparse
import yaml
import os
import sys
import subprocess
import logging
try:
    from tqdm import tqdm
except ImportError:
    tqdm = None

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [MainOrchestrator] - %(levelname)s - %(message)s'
)
logger = logging.getLogger("MainOrchestrator")

def load_config(config_path):
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config file not found: {config_path}")
    
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)

def run_blender_pipeline(config):
    # Setup path
    project_root = os.path.dirname(os.path.abspath(__file__))
    pipeline_script = os.path.join(project_root, "pipeline", "core.py")
    
    # Config parameters
    pipeline_conf = config.get('pipeline', {})
    output_base_dir = pipeline_conf.get('output_dir', './output')
    quality = pipeline_conf.get('quality', 'MEDIUM').upper()
    image_resolution = pipeline_conf.get('image_resolution', 2048)
    
    models = config.get('models', [])
    
    if not models:
        logger.warning("No models found in config.")
        return

    # Blender command detection (assuming it's in PATH)
    blender_exe = "blender"
    
    for i, model_entry in enumerate(models):
        input_path = model_entry.get('path')
        if not input_path:
            logger.warning(f"Model {i} without path. Skipping.")
            continue
            
        if not os.path.exists(input_path):
            logger.error(f"Input file not existing: {input_path}")
            continue
            
        # Determine specific output directory
        # core.py uses the output path to decide where to place files.
        # If we pass a folder, it will save inside it.
        
        logger.info(f"Starting processing for: {input_path}")
        
        # Command Construction
        # blender -b -P pipeline/core.py -- --input <in> --output <out> --decimation_presets <qual> --image_resolution <res>
        
        cmd = [
            blender_exe,
            "-b", # Background mode
            "-P", pipeline_script,
            "--", # Separator for python script arguments
            "--input", input_path,
            "--output", output_base_dir,
            "--decimation_presets", quality,
            "--image_resolution", str(image_resolution)
        ]
        
        # logger.info(f"Executing command: {' '.join(cmd)}")
        
        try:
            # We run in background with Popen to monitor progress
            with subprocess.Popen(
                cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.STDOUT, 
                text=True, 
                bufsize=1,
                encoding='utf-8', 
                errors='replace'
            ) as process:
                
                full_output = []
                pbar = None
                
                # Init progress bar if tqdm available
                if tqdm:
                    # Estimate phases: ~12 per loop
                    pbar = tqdm(total=12, desc=f"Processing {os.path.basename(input_path)}", unit="phase")
                
                for line in process.stdout:
                    line = line.strip()
                    full_output.append(line)
                    
                    # Dynamic Total Update: Catch "Starting optimization for X meshes..."
                    if "Starting optimization for" in line and "meshes" in line:
                        try:
                            # Expected format: "... Starting optimization for <N> meshes..."
                            parts = line.split("Starting optimization for")[1].split("meshes")[0].strip()
                            n_meshes = int(parts)
                            
                            # Calculation:
                            # 3 Initial Phases (1,2,3)
                            # 7 Loop Phases (5-11) * N
                            # 1 Final Phase (12)
                            # Total = 4 + (7 * n_meshes)
                            # (Note: Phase 4 matches Loop start implicitly)
                            
                            new_total = 4 + (7 * n_meshes)
                            if pbar is not None:
                                pbar.total = new_total
                                pbar.refresh()
                        except ValueError:
                            pass

                    # Update Progress on "Phase"
                    if "Phase" in line:
                         if pbar is not None:
                             pbar.update(1)
                             # Try to extract phase description
                             parts = line.split(":", 1)
                             if len(parts) > 1:
                                 pbar.set_postfix_str(parts[1].strip()[:40])
                    
                    # Also log meaningful lines (optional, to avoid total silence if no tqdm)
                    if tqdm is None:
                        logger.info(f"[Blender] {line}")
                
                if pbar is not None: 
                    pbar.close()
                
                return_code = process.wait()
                
                if return_code != 0:
                    logger.error(f"Error during elaboration of {input_path}")
                    logger.error("BLENDER OUTPUT:\n" + "\n".join(full_output))
                else:
                    logger.info(f"Completed: {input_path}")

        except Exception as e:
            logger.error(f"Generic error executing subprocess: {e}")

def main():
    parser = argparse.ArgumentParser(description="Mesh Optimizer Orchestrator")
    parser.add_argument("--config", type=str, required=True, help="Path to config.yaml")
    
    args = parser.parse_args()
    
    try:
        config = load_config(args.config)
        run_blender_pipeline(config)
    except Exception as e:
        logger.critical(f"Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()