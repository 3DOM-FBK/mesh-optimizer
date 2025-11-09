import os
import subprocess
import sys
import logging


# ===== Logger configuration =====
log_level = os.environ.get("LOGLEVEL", "INFO").upper()
log_format = '%(asctime)s - %(levelname)-8s - %(message)s'
logging.basicConfig(
    level=getattr(logging, log_level), 
    format=log_format,
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

logger.info("Pipeline start")
logger.info(f"Log level set to: {log_level}")



class MeshPipeline:
    """
    Core pipeline class for 3D mesh processing.
    Each step runs a separate Blender process to ensure isolation.
    """

    def __init__(self, input_file):
        """
        Args:
            blender_path (str): Path to the Blender executable.
            scripts_dir (str): Directory containing Blender Python scripts.
        """
        self.scripts_dir = "/app/pipeline"
        self.input_file = input_file
        self.basename = os.path.splitext(os.path.basename(input_file))[0]
        self.temp_dir = os.path.join("/tmp", self.basename)
        self.temp_input = os.path.join(self.temp_dir, "temp_model.glb")
        self.temp_remesh = os.path.join(self.temp_dir, "temp_model_remesh.glb")
        self.temp_remesh_decimate = os.path.join(self.temp_dir, "temp_model_remesh_decimate.glb")
        self.temp_decimate = os.path.join(self.temp_dir, "temp_model_decimate.glb")


    # ===== Utility =====
    def _run_blender_script(self, script_name, args=None):
        """
        Run a Blender Python script in background mode.

        Args:
            script_name (str): Name of the script (e.g., 'preprocess_model.py').
            args (list[str]): Additional arguments for the script.
        """
        script_path = os.path.join(self.scripts_dir, script_name)
        cmd = ["blender", "--background", "--python", script_path]

        if args:
            cmd.extend(args)

        res = subprocess.run(cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL
        )
        return res


    # ===== Pipeline Steps =====
    def preprocess_model(self, input_path):
        """Preprocess the input 3D model."""
        args = ["--", "--input_file", input_path]
        return self._run_blender_script("preprocess_model.py", args)


    def remesh_and_uv(self, dir_path):
        """Perform remeshing and UV generation."""
        args = ["--", "--dir_path", dir_path]
        return self._run_blender_script("remesh_and_uv.py", args)


    def decimate(self, input_path, output_path, quality="medium"):
        """Decimate the 3D mesh."""
        args = ["--", "--input_file", input_path, "--output_file", output_path, "--quality", str(quality)]
        return self._run_blender_script("decimate.py", args)
    

    def texture_generation(self, high_path, low_path, output_dir, image_size):
        """Texture Decimation"""
        args = ["--", "--high_path", high_path, "--low_path", low_path, "--output_dir", output_dir, "--image_size", str(image_size)]
        return self._run_blender_script("texture_generator.py", args)


    # ===== Full Pipeline =====
    def run_full_pipeline(self, output_dir, image_size=1024):
        """
        Run the full pipeline:
        1. Preprocess the model
        2. Perform remeshing
        3. If remeshing succeeds, decimate remeshed geometry
        4. Decimate original geometry
        5. Generate textures for each existing model stage
        """
        # os.makedirs(output_dir, exist_ok=True)

        logger.info("[1/4] Preprocessing model...")
        success_preprocess = self.preprocess_model(self.input_file)

        if not success_preprocess:
            logger.error("Preprocessing failed. Aborting pipeline.")
            return None

        logger.info("[2/4] Remeshing model...")
        success_remesh_and_uv = self.remesh_and_uv(self.temp_dir)

        if success_remesh_and_uv:
            logger.info("[3/4] Decimating remeshed geometry...")
            success_decimate_remesh = self.decimate(self.temp_remesh, self.temp_remesh_decimate)
            if not success_decimate_remesh:
                logger.error("Decimation of remesh failed.")
        else:
            logger.error("Remeshing failed, skipping remesh decimation.")

        logger.info("[4/4] Decimating original geometry...")
        success_decimate_original = self.decimate(self.temp_input, self.temp_decimate)
        if not success_decimate_original:
            logger.error("Decimation of original geometry failed.")

        # ===== Generate textures =====
        logger.info("Generating textures for available models...")

        # 1. Remesh
        if success_remesh_and_uv and os.path.exists(self.temp_remesh):
            remesh_tex_dir = os.path.join(output_dir, "remesh")
            os.makedirs(remesh_tex_dir, exist_ok=True)
            self.texture_generation(self.temp_input, self.temp_remesh, remesh_tex_dir, image_size)

        # 2. Remesh Decimation
        if success_remesh_and_uv and os.path.exists(self.temp_remesh_decimate):
            remesh_dec_tex_dir = os.path.join(output_dir, "remesh_decimation")
            os.makedirs(remesh_dec_tex_dir, exist_ok=True)
            self.texture_generation(self.temp_input, self.temp_remesh_decimate, remesh_dec_tex_dir, image_size)

        # 3. Original Decimation
        if success_decimate_original and os.path.exists(self.temp_decimate):
            decimation_tex_dir = os.path.join(output_dir, "decimation")
            os.makedirs(decimation_tex_dir, exist_ok=True)
            self.texture_generation(self.temp_input, self.temp_decimate, decimation_tex_dir, image_size)

        logger.info("--> Pipeline completed.")



if __name__ == "__main__":
    input_path = "/data/optimize/input/glb/sito_archeologico.glb"
    pipeline = MeshPipeline(input_path)

    
    pipeline.run_full_pipeline("/data/optimize/output")