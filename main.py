import argparse
import yaml
import os
import sys
from typing import Dict, Any, List

# Assume MeshPipeline class is correctly importable
try:
    from pipelines.core import MeshPipeline
except ImportError:
    print("WARNING: Could not import MeshPipeline from 'pipelines.core'. Please ensure the path is correct.", file=sys.stderr)
    sys.exit(1)


# ==============================================================================
# 1. Configuration Handling
# ==============================================================================

class ConfigurationError(Exception):
    """Custom exception for configuration related errors."""
    pass

class PipelineConfig:
    """
    Handles command-line arguments and loads the YAML configuration file.
    """
    @staticmethod
    def _parse_args() -> argparse.Namespace:
        """Parses command-line arguments."""
        parser = argparse.ArgumentParser(description="Optimization 3D Mesh Pipeline Runner.")
        parser.add_argument(
            "--config", 
            type=str, 
            required=True, 
            help="Configuration file (YAML) path."
        )
        return parser.parse_args()

    @staticmethod
    def _load_yaml_config(config_path: str) -> Dict[str, Any]:
        """Loads and validates the configuration from a YAML file."""
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Configuration file not found at: {config_path}")
            
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
            
        if not config or "pipeline" not in config or "models" not in config:
            raise ConfigurationError("YAML structure error. Missing 'pipeline' or 'models' section.")
            
        return config

    @classmethod
    def load(cls) -> Dict[str, Any]:
        """Entry point for loading and returning the full configuration."""
        args = cls._parse_args()
        return cls._load_yaml_config(args.config)


# ==============================================================================
# 2. Pipeline Execution Logic
# ==============================================================================

class PipelineRunner:
    """
    Manages the execution flow, iterating through models and running the pipeline.
    Status messages are printed to standard output/error, relying on core.py 
    for detailed logging of subprocesses.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """Initializes the runner with validated configuration parameters."""
        pipeline_params = config["pipeline"]
        
        self.output_dir: str = pipeline_params.get("output_dir")
        self.image_size: int = pipeline_params.get("image_size", 1024)
        self.quality: str = pipeline_params.get("quality", "medium")
        self.verbose: int = pipeline_params.get("verbose", 0)
        self.models: List[Dict[str, str]] = config.get("models", [])
        
        if not self.output_dir:
            raise ConfigurationError("The 'output_dir' is missing in the pipeline configuration.")

        os.makedirs(self.output_dir, exist_ok=True)


    def run(self) -> None:
        """
        Executes the mesh optimization pipeline for all models defined in the config.
        """
        if not self.models:
            print("WARNING: No models found in the configuration. Aborting.", file=sys.stderr)
            return

        for idx, model_data in enumerate(self.models):
            model_path = model_data.get("path")
            
            if not model_path or not os.path.exists(model_path):
                print(f"ERROR [{idx+1}/{len(self.models)}]: Model path invalid or not found: {model_path}. Skipping.", file=sys.stderr)
                continue

            basename = os.path.splitext(os.path.basename(model_path))[0]
            model_out_dir = os.path.join(self.output_dir, basename)
            os.makedirs(model_out_dir, exist_ok=True)

            try:
                # Initialize and run the MeshPipeline from core.py
                processor = MeshPipeline(model_path, self.verbose)
                processor.run_pipeline(
                    output_dir=model_out_dir,
                    image_size=self.image_size,
                    quality=self.quality
                )
            except Exception as e:
                # Use print to stderr for critical errors
                print(f"CRITICAL ERROR [{idx+1}/{len(self.models)}]: An unhandled error occurred during processing {basename}: {e}", file=sys.stderr) 


# ==============================================================================
# 3. Main Execution Function
# ==============================================================================

def main():
    """Main entry point."""
    try:
        # 1. Load Configuration
        config = PipelineConfig.load()
        
        # 2. Run Pipeline
        runner = PipelineRunner(config)
        runner.run()

    except (FileNotFoundError, ConfigurationError, Exception) as e:
        # Handle top-level errors (e.g., config file missing)
        print(f"\nFATAL CONFIGURATION/SETUP ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()