import os
import subprocess
import sys
import logging
import shutil
from contextlib import contextmanager

# ==============================================================================
# 1. Configuration and Constants
# ==============================================================================

# Blender executable path (assuming 'blender' is in the PATH)
# For production, it's safer to use an absolute path or an env var.
BLENDER_EXECUTABLE = "blender"
SCRIPTS_DIR = "/app/pipelines"
TEMP_BASE_DIR = "/tmp"

# ===== Logger configuration =====
LOG_LEVEL = os.environ.get("LOGLEVEL", "INFO").upper()
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)-8s - %(message)s'
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL), 
    format=LOG_FORMAT,
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("MeshPipeline")

logger.info("Pipeline initialization started")
logger.info(f"Log level set to: {LOG_LEVEL}")


@contextmanager
def temporary_directory(basename):
    """
    A context manager to safely create and automatically clean up a temporary directory.
    """
    temp_dir = os.path.join(TEMP_BASE_DIR, basename)
    
    # Clean up before creating to ensure a fresh start if the directory was left behind
    if os.path.exists(temp_dir):
        try:
            shutil.rmtree(temp_dir)
        except OSError as e:
            logger.error(f"Error cleaning up existing temp dir {temp_dir}: {e}")
            raise
            
    try:
        os.makedirs(temp_dir, exist_ok=False)
        logger.debug(f"Created temporary directory: {temp_dir}")
        yield temp_dir
    finally:
        # Final cleanup attempt
        if os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
                logger.debug(f"Cleaned up temporary directory: {temp_dir}")
            except OSError as e:
                logger.error(f"Error during final cleanup of {temp_dir}: {e}")


# ==============================================================================
# 2. Core Pipeline Class
# ==============================================================================

class MeshPipeline:
    """
    Core pipeline class for 3D mesh processing.
    Each step runs a separate Blender process to ensure isolation.
    """

    def __init__(self, input_file, verbose=0):
        """
        Initializes the pipeline with input file and configuration.

        Args:
            input_file (str): Path to the input 3D model file (e.g., .glb).
            verbose (int): Verbosity level (0 for silent, 1 for Blender output).
        """
        if not os.path.exists(input_file):
            raise FileNotFoundError(f"Input file not found: {input_file}")
            
        self.input_file = input_file
        self.basename = os.path.splitext(os.path.basename(input_file))[0]
        self.verbose = verbose
        # The temporary paths will be resolved within the run_pipeline context
        # but these names are used for consistency.
        self.TEMP_INPUT_NAME = "temp_model.glb"
        self.TEMP_REMESH_NAME = "remesh.glb"
        self.TEMP_DECIMATE_NAME = "decimate.glb"


    # ===== Utility Methods (Private) =====
    def _run_blender_script(self, script_name: str, args: list = None) -> None:
        """
        Run a Blender Python script in background mode.

        Args:
            script_name (str): Name of the script (e.g., 'preprocess_model.py').
            args (list[str]): Additional arguments for the script.
        
        Raises:
            subprocess.CalledProcessError: If the Blender process returns a non-zero exit code.
        """
        script_path = os.path.join(SCRIPTS_DIR, script_name)
        cmd = [BLENDER_EXECUTABLE, "--background", "--python", script_path]

        if args:
            cmd.extend(args)

        logger.debug(f"Executing: {' '.join(cmd)}")
        
        try:
            if self.verbose == 1:
                # Runs with output directed to stdout/stderr
                subprocess.run(cmd, check=True)
            else:
                # Runs silently, redirecting output to /dev/null
                subprocess.run(cmd, 
                               check=True,
                               stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL,
                               stdin=subprocess.DEVNULL)
            logger.debug(f"Successfully executed {script_name}")
        except subprocess.CalledProcessError as e:
            logger.error(f"Blender script '{script_name}' failed with exit code {e.returncode}.")
            # Re-raise the exception to be caught by the main pipeline logic
            raise


    # ===== Pipeline Steps (Private) =====
    
    def _preprocess_model(self, input_path: str) -> None:
        """Preprocess the input 3D model."""
        logger.info(f"[1/4] Preprocessing model [{self.basename}]...")
        # Note: preprocess_model.py is expected to output a copy to be used
        # in the pipeline's temp space, e.g., to {temp_dir}/{self.TEMP_INPUT_NAME}
        args = ["--", "--input_file", input_path]
        self._run_blender_script("preprocess_model.py", args)
        logger.info("Preprocessing step finished.")


    def _remesh(self, temp_dir: str) -> None:
        """Perform remeshing and UV generation."""
        logger.info("[2/4] Remeshing model...")
        # remesh.py is expected to use files in {temp_dir} and output 
        # the result to {temp_dir}/{self.TEMP_REMESH_NAME}
        args = ["--", "--dir_path", temp_dir]
        self._run_blender_script("remesh.py", args)
        logger.info("Remeshing step finished.")


    def _decimate(self, input_path: str, output_path: str, quality: str) -> None:
        """Decimate the 3D mesh."""
        logger.info("[3/4] Decimating original geometry...")
        args = ["--", "--input_file", input_path, "--output_file", output_path, "--quality", quality]
        self._run_blender_script("decimate.py", args)
        logger.info("Decimation step finished.")


    def _texture_generation(self, high_path: str, low_path: str, output_dir: str, image_size: int, check_emission: bool = False) -> None:
        """Generate textures by baking high-poly to low-poly."""
        logger.info("[4/4] Generating textures...")
        args = [
            "--", 
            "--high_path", high_path, 
            "--low_path", low_path, 
            "--output_dir", output_dir, 
            "--image_size", str(image_size)
        ]
        if check_emission:
            args.append("--check_emission")
            
        self._run_blender_script("texture_generator.py", args)
        logger.info("Texture generation step finished.")


    # ==============================================================================
    # 3. Full Pipeline Execution
    # ==============================================================================

    def run_pipeline(self, output_dir: str, image_size: int = 1024, quality: str = "medium") -> bool:
        """
        Run the full 3D mesh processing pipeline.

        Args:
            output_dir (str): The final destination directory for outputs.
            image_size (int): Resolution for baked textures.
            quality (str): Decimation quality ('low', 'medium', 'high').
            
        Returns:
            bool: True if the pipeline completed successfully, False otherwise.
        """
        
        # Ensure output directory exists
        os.makedirs(output_dir, exist_ok=True)
        
        pipeline_success = False
        
        # Use the context manager for safe temporary folder handling
        with temporary_directory(self.basename) as temp_dir:
            
            # Full temporary paths
            temp_input_path = os.path.join(temp_dir, self.TEMP_INPUT_NAME)
            temp_remesh_path = os.path.join(temp_dir, self.TEMP_REMESH_NAME)
            temp_decimate_path = os.path.join(temp_dir, self.TEMP_DECIMATE_NAME)

            try:
                # 1. Preprocess
                # Note: The preprocess script must copy the input file to temp_input_path
                self._preprocess_model(self.input_file) 

                # # 2. Remesh
                # self._remesh(temp_dir)
                
                # # Copy remeshed output to final directory for external use
                # if os.path.exists(temp_remesh_path):
                #     remesh_final_dir = os.path.join(output_dir, "remesh")
                #     os.makedirs(remesh_final_dir, exist_ok=True)
                #     shutil.copy(temp_remesh_path, os.path.join(remesh_final_dir, self.TEMP_REMESH_NAME))
                #     logger.info(f"Remesh output copied to {remesh_final_dir}")
                # else:
                #     logger.warning("Remesh output file not found after step.")

                # 3. Decimate Original Geometry (High-poly source for baking)
                self._decimate(temp_input_path, temp_decimate_path, quality)

                # 4. Generate Textures (Bake from High-poly to Low-poly/Decimated)
                # The assumption is that `temp_input_path` holds the high-poly geometry 
                # (or the preprocessed version before decimation) and `temp_decimate_path` 
                # is the resulting low-poly mesh.
                if os.path.exists(temp_input_path) and os.path.exists(temp_decimate_path):
                    decimation_final_dir = os.path.join(output_dir, "decimation")
                    os.makedirs(decimation_final_dir, exist_ok=True)
                    self._texture_generation(
                        high_path=temp_input_path, 
                        low_path=temp_decimate_path, 
                        output_dir=decimation_final_dir, 
                        image_size=image_size, 
                        check_emission=True
                    )
                    pipeline_success = True
                else:
                    logger.error("Missing high or low poly mesh for texture generation. Skipping step.")


            except subprocess.CalledProcessError:
                logger.error("A Blender step failed. Aborting pipeline.")
            except FileNotFoundError as e:
                logger.error(f"Required file not found: {e}. Aborting pipeline.")
            except Exception as e:
                logger.critical(f"An unexpected error occurred during pipeline execution: {e}")
            finally:
                if pipeline_success:
                    logger.info("--> Pipeline completed successfully.")
                else:
                    logger.warning("--> Pipeline completed with errors or incomplete.")
                
                return pipeline_success