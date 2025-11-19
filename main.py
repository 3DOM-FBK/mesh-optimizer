import argparse
import yaml
import os
import sys
from datetime import datetime

from pipelines.core import MeshPipeline


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

    config["models"] = models
    return config


if __name__ == "__main__":
    args = parse_args()

    config = load_config(args.config)
    image_size = config["pipeline"]["image_size"]
    output_dir = config["pipeline"]["output_dir"]
    quality = config["pipeline"]["quality"]
    verbose = config["pipeline"]["verbose"]

    for idx, model in enumerate(config["models"]):
        path = model["path"]
        processor = MeshPipeline(path, verbose)

        # Generate model output dir
        basename = os.path.splitext(os.path.basename(model["path"]))[0]
        model_out_dir = os.path.join(output_dir, basename)
        os.makedirs(model_out_dir, exist_ok=True)

        processor.run_pipeline(
            output_dir=model_out_dir,
            image_size=image_size,
            quality=quality
        )