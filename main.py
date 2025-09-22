import argparse
import yaml
import logging
import os
import sys
import time
from datetime import datetime
import subprocess


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


# ===== Function: parse_args =====
def parse_args():
    parser = argparse.ArgumentParser(description="Optimization 3D mesh pipeline")
    parser.add_argument(
        "--config", 
        type=str, 
        required=True, 
        help="Configuration file (YAML) path"
    )
    return parser.parse_args()


# ===== Function: load_config =====
def load_config(config_path="config.yaml"):
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    models = config.get("models", [])
    for m in models:
        if "name" not in m or not m["name"]:
            m["name"] = os.path.splitext(os.path.basename(m["path"]))[0]
        if "basecolor_img" not in m:
            m["basecolor_img"] = "None"

    config["models"] = models
    return config


# ===== Function: run_blender_cmd =====
def run_blender_cmd(script_path, params):
    cmd = ["blender", "-b", "--python", script_path, "--"]

    if params:
        for key, value in params.items():
            cmd.append(f"--{key}")
            if value is not None:
                cmd.append(str(value))

    res = subprocess.run(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL
    )

    return res


class PipelineProcessor:
    def __init__(self, config, idx):
        self.idx = idx

        self.model = config["models"][self.idx]
        self.model_path = self.model["path"]
        self.model_name = self.model["name"]
        self.basecolor_img = self.model["basecolor_img"]
        self.decimation_ratio = config["pipeline"]["decimate_ratio"]
        self.decimation_ratio = config["pipeline"]["decimate_ratio"]
        self.image_resolution = config["pipeline"]["image_resolution"]
        self.tmp_basecolor = "/tmp/diffuse.png"
        self.output_folder = config["pipeline"]["output_folder"]
        self.output_format = config["pipeline"]["output_format"]
    
    
    def run_cleanup(self):
        logger.info("-> Cleanup geometry step")

        script_path = "/workspace/python/cleanup_geo.py"
        params = {"input_file": self.model_path, "basecolor_img": self.basecolor_img, "bake_image_size": self.image_resolution}
        res = run_blender_cmd(script_path, params)

        if res.returncode == 0:
            logger.info("Cleanup done")
        else:
            logger.error("Error during cleanup step")
    

    def run_remesh(self):
        logger.info("-> Remesh geometry step")

        script_path = "/workspace/python/remesh.py"
        params = {"input_file": "/tmp/model.obj", "bake_image_size": self.image_resolution, "basecolor_img": self.tmp_basecolor }
        res = run_blender_cmd(script_path, params)

        if res.returncode == 0:
            logger.info("Remesh done")
        else:
            logger.error("Error during remesh step")
    

    def run_decimate(self):
        logger.info("-> Decimate geometry step")

        script_path = "/workspace/python/decimate.py"
        params = {"input_file": "/tmp/model.obj", "decimate_ratio": self.decimation_ratio}
        res = run_blender_cmd(script_path, params)

        if res.returncode == 0:
            logger.info("Decimate done")
        else:
            logger.error("Error during decimate step")

    
    def improve_material(self):
        logger.info("-> Improve material step")

        script_path = "/workspace/python/improve_material.py"
        params = {"input_file": "/tmp/model.obj", "bake_image_size": self.image_resolution, "basecolor_img": self.tmp_basecolor}
        res = run_blender_cmd(script_path, params)

        if res.returncode == 0:
            logger.info("Improve material done")
        else:
            logger.error("Error during improve material step")
    

    def format_conversion(self):
        logger.info(f"-> Format conversion step (--> {self.output_format})")

        script_path = "/workspace/python/file_conversion.py"
        params = {"input_file": "/tmp/model.obj", "output_folder": self.output_folder, "output_format": self.output_format, "model_name": self.model_name}
        res = run_blender_cmd(script_path, params)

        if res.returncode == 0:
            logger.info("File conversion done")
        else:
            logger.error("Error during file conversion step")
    

    def run_pipeline(self):
        logger.info(f"Process mesh: {self.model_name}")

        # Cleanup geometry
        self.run_cleanup()

        # Remesh geometry
        if (config["pipeline"]["remesh"]):
            self.run_remesh()
        
        # Decimate geometry
        if (config["pipeline"]["decimate"]):
            self.run_decimate()
        
        # Improve material
        if (config["pipeline"]["improve_material"]):
            self.improve_material()
        
        # Format conversion
        self.format_conversion()



if __name__ == "__main__":
    args = parse_args()

    config = load_config(args.config)

    for idx, _ in enumerate(config["models"]):
        processor = PipelineProcessor(config, idx)

        processor.run_pipeline()
    

    
