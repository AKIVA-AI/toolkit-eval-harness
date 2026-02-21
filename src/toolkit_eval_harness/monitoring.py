"""
Monitoring and health checks for Toolkit Eval Harness
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional


class HealthCheck:
    """Health check utilities"""
    
    @staticmethod
    def check_system() -> Dict[str, Any]:
        """Check system health"""
        try:
            from . import __version__
            
            return {
                "status": "healthy",
                "version": __version__,
                "timestamp": datetime.utcnow().isoformat()
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
    
    @staticmethod
    def check_suite_pack(pack_path: Path) -> Dict[str, Any]:
        """Check if suite pack is valid"""
        try:
            if not pack_path.exists():
                return {
                    "status": "not_found",
                    "path": str(pack_path),
                    "timestamp": datetime.utcnow().isoformat()
                }
            
            # Basic validation - check if it's a valid zip
            import zipfile
            if not zipfile.is_zipfile(pack_path):
                return {
                    "status": "invalid_format",
                    "path": str(pack_path),
                    "timestamp": datetime.utcnow().isoformat()
                }
            
            return {
                "status": "valid",
                "path": str(pack_path),
                "size_bytes": pack_path.stat().st_size,
                "timestamp": datetime.utcnow().isoformat()
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "path": str(pack_path),
                "timestamp": datetime.utcnow().isoformat()
            }


class EvaluationMetrics:
    """Track evaluation metrics"""
    
    def __init__(self):
        self.metrics = {
            "evaluations_run": 0,
            "total_test_cases": 0,
            "passed_test_cases": 0,
            "failed_test_cases": 0,
            "regressions_detected": 0,
            "suite_packs_created": 0,
        }
    
    def record_evaluation(self, total: int, passed: int):
        """Record evaluation results"""
        self.metrics["evaluations_run"] += 1
        self.metrics["total_test_cases"] += total
        self.metrics["passed_test_cases"] += passed
        self.metrics["failed_test_cases"] += (total - passed)
    
    def record_regression(self):
        """Record regression detection"""
        self.metrics["regressions_detected"] += 1
    
    def record_suite_pack_creation(self):
        """Record suite pack creation"""
        self.metrics["suite_packs_created"] += 1
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get current metrics"""
        return {
            **self.metrics,
            "pass_rate": (
                self.metrics["passed_test_cases"] / self.metrics["total_test_cases"]
                if self.metrics["total_test_cases"] > 0
                else 0.0
            ),
            "timestamp": datetime.utcnow().isoformat()
        }
    
    def reset(self):
        """Reset all metrics"""
        for key in self.metrics:
            self.metrics[key] = 0


# Global metrics instance
_metrics = EvaluationMetrics()


def get_metrics() -> Dict[str, Any]:
    """Get global metrics"""
    return _metrics.get_metrics()


def get_health_status(pack_path: Optional[Path] = None) -> Dict[str, Any]:
    """Get comprehensive health status"""
    status = {
        "system": HealthCheck.check_system(),
        "metrics": get_metrics()
    }
    
    if pack_path:
        status["suite_pack"] = HealthCheck.check_suite_pack(pack_path)
    
    return status


