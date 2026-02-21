"""
Configuration management for Toolkit Eval Harness
"""

import os
from pathlib import Path
from typing import Optional


class Config:
    """Configuration settings for Eval Harness"""
    
    # General Settings
    EVAL_HARNESS_HOME: Path = Path(os.getenv("EVAL_HARNESS_HOME", "/app"))
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    VERBOSE: bool = os.getenv("VERBOSE", "false").lower() == "true"
    
    # Suite Pack Settings
    ENABLE_SIGNING: bool = os.getenv("ENABLE_SIGNING", "false").lower() == "true"
    SIGNING_KEY_PATH: Optional[str] = os.getenv("SIGNING_KEY_PATH")
    VERIFY_SIGNATURES: bool = os.getenv("VERIFY_SIGNATURES", "true").lower() == "true"
    
    # Evaluation Settings
    DEFAULT_SCORER: str = os.getenv("DEFAULT_SCORER", "exact_match")
    PARALLEL_WORKERS: int = int(os.getenv("PARALLEL_WORKERS", "4"))
    BATCH_SIZE: int = int(os.getenv("BATCH_SIZE", "100"))
    
    # Regression Settings
    REGRESSION_THRESHOLD: float = float(os.getenv("REGRESSION_THRESHOLD", "0.05"))
    FAIL_ON_REGRESSION: bool = os.getenv("FAIL_ON_REGRESSION", "true").lower() == "true"
    
    # Output Settings
    OUTPUT_FORMAT: str = os.getenv("OUTPUT_FORMAT", "json")
    SAVE_PREDICTIONS: bool = os.getenv("SAVE_PREDICTIONS", "true").lower() == "true"
    SAVE_DETAILED_RESULTS: bool = os.getenv("SAVE_DETAILED_RESULTS", "true").lower() == "true"
    
    # Performance
    MAX_MEMORY_MB: int = int(os.getenv("MAX_MEMORY_MB", "4096"))
    TIMEOUT_SECONDS: int = int(os.getenv("TIMEOUT_SECONDS", "300"))
    
    @classmethod
    def validate(cls) -> None:
        """Validate configuration settings"""
        if not 0 <= cls.REGRESSION_THRESHOLD <= 1:
            raise ValueError("REGRESSION_THRESHOLD must be between 0 and 1")
        
        if cls.PARALLEL_WORKERS < 1:
            raise ValueError("PARALLEL_WORKERS must be positive")
        
        if cls.BATCH_SIZE < 1:
            raise ValueError("BATCH_SIZE must be positive")
        
        if cls.MAX_MEMORY_MB < 1:
            raise ValueError("MAX_MEMORY_MB must be positive")
        
        if cls.TIMEOUT_SECONDS < 1:
            raise ValueError("TIMEOUT_SECONDS must be positive")
        
        valid_log_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if cls.LOG_LEVEL.upper() not in valid_log_levels:
            raise ValueError(f"LOG_LEVEL must be one of {valid_log_levels}")
        
        valid_scorers = ["exact_match", "json_schema", "custom"]
        if cls.DEFAULT_SCORER not in valid_scorers:
            raise ValueError(f"DEFAULT_SCORER must be one of {valid_scorers}")
    
    @classmethod
    def get_config_dict(cls) -> dict:
        """Get configuration as dictionary"""
        return {
            "general": {
                "home": str(cls.EVAL_HARNESS_HOME),
                "log_level": cls.LOG_LEVEL,
                "verbose": cls.VERBOSE,
            },
            "suite_packs": {
                "enable_signing": cls.ENABLE_SIGNING,
                "verify_signatures": cls.VERIFY_SIGNATURES,
            },
            "evaluation": {
                "default_scorer": cls.DEFAULT_SCORER,
                "parallel_workers": cls.PARALLEL_WORKERS,
                "batch_size": cls.BATCH_SIZE,
            },
            "regression": {
                "threshold": cls.REGRESSION_THRESHOLD,
                "fail_on_regression": cls.FAIL_ON_REGRESSION,
            },
            "performance": {
                "max_memory_mb": cls.MAX_MEMORY_MB,
                "timeout_seconds": cls.TIMEOUT_SECONDS,
            },
        }


# Validate configuration on import
Config.validate()


