import os
import subprocess
import sys
import logging
import shutil


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

    def __init__(self, input_file, verbose=0):
        """
        Args:
            blender_path (str): Path to the Blender executable.
            scripts_dir (str): Directory containing Blender Python scripts.
        """
        self.scripts_dir = "/app/pipelines"
        self.input_file = input_file
        self.basename = os.path.splitext(os.path.basename(input_file))[0]
        self.temp_dir = os.path.join("/tmp", self.basename)
        self.temp_input = os.path.join(self.temp_dir, "temp_model.glb")
        self.temp_remesh = os.path.join(self.temp_dir, "remesh.glb")
        self.temp_decimate = os.path.join(self.temp_dir, "decimate.glb")

        self.verbose = verbose


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

        if (self.verbose == 1):
            res = subprocess.run(cmd)
        else:
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


    def remesh(self, dir_path):
        """Perform remeshing and UV generation."""
        args = ["--", "--dir_path", dir_path]
        return self._run_blender_script("remesh.py", args)


    def decimate(self, input_path, output_path, quality="medium"):
        """Decimate the 3D mesh."""
        args = ["--", "--input_file", input_path, "--output_file", output_path, "--quality", str(quality)]
        return self._run_blender_script("decimate.py", args)
    

    def texture_generation(self, high_path, low_path, output_dir, image_size, check_emission=False):
        """Texture Decimation"""
        if (check_emission):
            args = ["--", "--high_path", high_path, "--low_path", low_path, "--output_dir", output_dir, "--image_size", str(image_size), "--check_emission"]
        else:
            args = ["--", "--high_path", high_path, "--low_path", low_path, "--output_dir", output_dir, "--image_size", str(image_size)]
        return self._run_blender_script("texture_generator.py", args)
    

    def clear_tmp_folder(self, tmp_dir="/tmp"):
        """
        Delete all files and folders inside the specified tmp directory.
        """
        if not os.path.exists(tmp_dir):
            return

        for entry in os.listdir(tmp_dir):
            path = os.path.join(tmp_dir, entry)
            try:
                if os.path.isfile(path) or os.path.islink(path):
                    os.remove(path)  # remove file or symlink
                elif os.path.isdir(path):
                    shutil.rmtree(path)  # remove directory and all its contents
            except Exception as e:
                # optionally log or pass
                pass


# ===== Full Pipeline =====
    def run_pipeline(self, output_dir, image_size=1024, quality="medium"):
        """
        Run the full pipeline:
        1. Preprocess the model
        2. Perform remeshing
        4. Decimate original geometry
        5. Generate textures
        """
        logger.info(f"[1/4] Preprocessing model [{self.basename}]...")
        success_preprocess = self.preprocess_model(self.input_file)

        if not success_preprocess:
            logger.error("Preprocessing failed. Aborting pipeline.")
            return None

        logger.info("[2/4] Remeshing model...")
        if self.remesh(self.temp_dir):
            remesh_dir = os.path.join(output_dir, "remesh")
            os.makedirs(remesh_dir, exist_ok=True)
            src_file = os.path.join(self.temp_dir, "remesh.glb")
            dst_folder = os.path.join(remesh_dir, "remesh.glb")
            shutil.copy(src_file, dst_folder)

        logger.info("[3/4] Decimating original geometry...")
        success_decimate_original = self.decimate(self.temp_input, self.temp_decimate, quality)
        if not success_decimate_original:
            logger.error("Decimation of original geometry failed.")

        # ===== Generate textures =====
        logger.info("[4/4] Generating textures...")
        # 3. Original Decimation
        if success_decimate_original and os.path.exists(self.temp_decimate):
            decimation_dir = os.path.join(output_dir, "decimation")
            os.makedirs(decimation_dir, exist_ok=True)
            self.texture_generation(self.temp_input, self.temp_decimate, decimation_dir, image_size, check_emission=True)

        self.clear_tmp_folder()

        logger.info("--> Pipeline completed.")