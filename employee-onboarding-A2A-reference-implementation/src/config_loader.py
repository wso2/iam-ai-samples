"""
Configuration loader.
Loads application configuration from YAML file with environment variable resolution.
"""

import os
import re
import yaml
import structlog
from typing import Any

logger = structlog.get_logger()


def resolve_env_vars(obj: Any) -> Any:
    """
    Recursively resolve ${VAR} placeholders with environment variables.
    """
    if isinstance(obj, str):
        # Pattern to match ${VAR_NAME}
        pattern = r'\$\{([^}]+)\}'
        
        def replacer(match):
            var_name = match.group(1)
            value = os.getenv(var_name, "")
            if not value:
                logger.warning("env_var_not_found", var=var_name)
            return value
        
        return re.sub(pattern, replacer, obj)
    
    elif isinstance(obj, dict):
        return {key: resolve_env_vars(value) for key, value in obj.items()}
    
    elif isinstance(obj, list):
        return [resolve_env_vars(item) for item in obj]
    
    else:
        return obj


def load_yaml_config(path: str = "config.yaml") -> dict[str, Any]:
    """
    Load configuration from a YAML file.
    Resolves ${VAR} placeholders with environment variables from .env
    
    Args:
        path: Path to the YAML file
        
    Returns:
        Configuration dictionary with resolved env vars
    """
    # Load .env file first (force reload to get latest values)
    from dotenv import load_dotenv
    load_dotenv(override=True)
    
    # Debug: Check if HR_AGENT_ID is loaded correctly
    hr_id = os.getenv("HR_AGENT_ID")
    if hr_id:
        logger.info(f"Loaded HR_AGENT_ID from env: {hr_id}")
    else:
        logger.warning("HR_AGENT_ID not found in env")
    
    try:
        with open(path, "r") as f:
            config = yaml.safe_load(f)
        
        # Resolve environment variables
        config = resolve_env_vars(config)
        
        logger.info("config_loaded", path=path)
        return config
    except FileNotFoundError:
        logger.warning("config_file_not_found", path=path)
        return {}
    except Exception as e:
        logger.error("config_load_error", path=path, error=str(e))
        return {}
