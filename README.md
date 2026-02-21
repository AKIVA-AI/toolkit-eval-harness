# Toolkit Eval Harness

Enterprise-grade evaluation framework for AI/ML models with versioned test suites, deterministic scoring, and CI/CD integration for regression testing.

## Overview

The Toolkit Eval Harness is a lightweight, powerful evaluation tool designed for AI/ML engineers to version "golden" task suites, score predictions with deterministic metrics, and produce CI-friendly JSON reports with regression comparisons. It complements Neural Forge model lifecycle gates and provides a solid foundation for model evaluation in production environments.

## Key Features

### ðŸ“‹ **Test Suite Management**
- **Versioned Test Suites**: Immutable, version-controlled evaluation datasets
- **Deterministic Scoring**: Consistent, reproducible evaluation metrics
- **Suite Packs**: Compressed, hash-verified test suite packages
- **Digital Signatures**: Optional cryptographic signing for integrity verification

### ðŸŽ¯ **Comprehensive Evaluation**
- **Multiple Scoring Methods**: Exact match, JSON schema validation, custom metrics
- **Flexible Test Cases**: Support for various input/output formats
- **Tagging System**: Organize tests by category, difficulty, or use case
- **Batch Processing**: Efficient evaluation of large test suites

### ðŸš€ **Enterprise Integration**
- **CI/CD Friendly**: JSON reports with exit codes for pipeline integration
- **Regression Detection**: Automated comparison against baseline evaluations
- **Audit Trails**: Complete evaluation history and provenance tracking
- **Performance Metrics**: Latency, throughput, and resource usage tracking

### ðŸ”’ **Security & Compliance**
- **Package Signing**: Ed25519 cryptographic signatures for integrity
- **Hash Verification**: SHA-256 checksums for all packages
- **Access Control**: Role-based permissions for suite management
- **Audit Logging**: Complete evaluation audit trails

## Architecture

```
â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”    â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”    â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
â”‚   Test Cases    â”‚â”€â”€â”€â–¶â”‚  Suite Builder  â”‚â”€â”€â”€â–¶â”‚  Suite Pack     â”‚
â”‚                 â”‚    â”‚                 â”‚    â”‚                 â”‚
â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜    â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜    â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
                                                         â”‚
â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”    â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”    â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
â”‚   Predictions   â”‚â”€â”€â”€â–¶â”‚  Evaluation     â”‚â—€â”€â”€â”€â”‚  Suite Pack     â”‚
â”‚                 â”‚    â”‚                 â”‚    â”‚                 â”‚
â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜    â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜    â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
                                 â”‚
                                 â–¼
                       â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
                       â”‚  Evaluation     â”‚
                       â”‚     Report      â”‚
                       â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
```

## Quick Start

### Installation

```bash
# Install from source
git clone https://github.com/<org>/eval-harness.git
cd eval-harness
pip install -e ".[dev]"

# Install with signing support
pip install -e ".[signing]"

# Install in production
pip install toolkit-eval-harness
```

### Basic Usage

```bash
# 1. Create a test suite pack
toolkit-eval pack create --suite-dir examples/suite --out packs/suite.zip

# 2. Verify pack integrity
toolkit-eval pack verify --suite packs/suite.zip

# 3. Run evaluation
toolkit-eval run --suite packs/suite.zip --predictions examples/preds.jsonl --out report.json

# 4. Compare with baseline (CI gating)
toolkit-eval compare --baseline baseline.json --candidate report.json
```

## Detailed Usage

### 1. Creating Test Suites

#### Suite Directory Structure
```
my_suite/
â”œâ”€â”€ suite.json          # Suite metadata
â”œâ”€â”€ cases.jsonl         # Test cases (JSONL format)
â””â”€â”€ assets/             # Optional supporting files
    â”œâ”€â”€ images/
    â”œâ”€â”€ documents/
    â””â”€â”€ reference_data/
```

#### Suite Metadata (`suite.json`)
```json
{
  "schema_version": 1,
  "name": "customer-support-evaluation",
  "description": "Comprehensive evaluation for customer support LLM responses",
  "version": "1.2.0",
  "created_at": "2024-01-15T10:30:00Z",
  "author": "ai-team@company.com",
  "tags": ["customer-support", "safety", "accuracy"],
  "scoring": {
    "json_schema": {
      "required_keys": ["status", "result", "confidence"],
      "optional_keys": ["notes", "escalation_needed"],
      "allow_extra_keys": true,
      "key_validation": {
        "status": {
          "type": "string",
          "allowed_values": ["ok", "error", "escalate"]
        },
        "result": {
          "type": "object",
          "required_keys": ["category", "action"]
        },
        "confidence": {
          "type": "number",
          "range": [0.0, 1.0]
        }
      }
    },
    "custom_metrics": [
      {
        "name": "response_time",
        "type": "threshold",
        "max_value": 5000
      },
      {
        "name": "sentiment_score",
        "type": "range",
        "min_value": 0.6
      }
    ]
  },
  "requirements": {
    "min_cases": 100,
    "max_cases": 10000,
    "required_tags": ["functional", "edge_case"]
  },
  "metadata": {
    "domain": "customer_support",
    "language": "en",
    "model_type": "chat_completion",
    "evaluation_type": "automated"
  }
}
```

#### Test Cases (`cases.jsonl`)
```json
{"id":"cs001","input":{"prompt":"How do I return an item?"},"expected":{"status":"ok","result":{"category":"returns","action":"provide_instructions"}},"tags":["functional","common"],"difficulty":"easy"}
{"id":"cs002","input":{"prompt":"My order arrived damaged, what should I do?"},"expected":{"status":"escalate","result":{"category":"damage","action":"create_ticket"}},"tags":["functional","escalation"],"difficulty":"medium"}
{"id":"cs003","input":{"prompt":"Can you help me track my package?"},"expected":{"status":"ok","result":{"category":"tracking","action":"provide_status"}},"tags":["functional","common"],"difficulty":"easy"}
{"id":"cs004","input":{"prompt":"I want to cancel my subscription and get a refund"},"expected":{"status":"escalate","result":{"category":"billing","action":"process_refund"}},"tags":["functional","billing","escalation"],"difficulty":"hard"}
{"id":"cs005","input":{"prompt":"The product doesn't match the description online"},"expected":{"status":"ok","result":{"category":"complaint","action":"offer_solution"}},"tags":["functional","complaint"],"difficulty":"medium"}
```

### 2. Suite Pack Creation

#### Create Pack
```bash
toolkit-eval pack create \
  --suite-dir my_suite \
  --out packs/customer-support-v1.2.0.zip \
  --include-assets \
  --compress-level 6
```

#### Generated Pack Structure
```
customer-support-v1.2.0.zip
â”œâ”€â”€ suite.json          # Suite metadata
â”œâ”€â”€ cases.jsonl         # Test cases
â”œâ”€â”€ checksum.json       # SHA-256 hashes
â”œâ”€â”€ assets/             # Supporting files
â”‚   â”œâ”€â”€ images/
â”‚   â””â”€â”€ documents/
â””â”€â”€ manifest.json       # Pack manifest
```

#### Verify Pack Integrity
```bash
toolkit-eval pack verify \
  --suite packs/customer-support-v1.2.0.zip \
  --check-all-hashes \
  --validate-schema
```

### 3. Digital Signing (Optional)

#### Generate Keys
```bash
toolkit-eval keygen \
  --private-key toolkit_eval_private.pem \
  --public-key toolkit_eval_public.pem \
  --key-type ed25519
```

#### Sign Pack
```bash
toolkit-eval pack sign \
  --suite packs/customer-support-v1.2.0.zip \
  --private-key toolkit_eval_private.pem \
  --out packs/customer-support-v1.2.0.sig.json
```

#### Verify Signature
```bash
toolkit-eval pack verify-signature \
  --suite packs/customer-support-v1.2.0.zip \
  --signature packs/customer-support-v1.2.0.sig.json \
  --public-key toolkit_eval_public.pem
```

### 4. Running Evaluations

#### Prediction Format (`predictions.jsonl`)
```json
{"id":"cs001","prediction":{"status":"ok","result":{"category":"returns","action":"provide_instructions"},"confidence":0.95},"latency_ms":1250,"metadata":{"model":"gpt-4","temperature":0.7}}
{"id":"cs002","prediction":{"status":"escalate","result":{"category":"damage","action":"create_ticket"},"confidence":0.88},"latency_ms":2100,"metadata":{"model":"gpt-4","temperature":0.7}}
{"id":"cs003","prediction":{"status":"ok","result":{"category":"tracking","action":"provide_status"},"confidence":0.92},"latency_ms":980,"metadata":{"model":"gpt-4","temperature":0.7}}
{"id":"cs004","prediction":{"status":"escalate","result":{"category":"billing","action":"process_refund"},"confidence":0.91},"latency_ms":1850,"metadata":{"model":"gpt-4","temperature":0.7}}
{"id":"cs005","prediction":{"status":"ok","result":{"category":"complaint","action":"offer_solution"},"confidence":0.87},"latency_ms":1450,"metadata":{"model":"gpt-4","temperature":0.7}}
```

#### Run Evaluation
```bash
toolkit-eval run \
  --suite packs/customer-support-v1.2.0.zip \
  --predictions examples/preds.jsonl \
  --out evaluation_report.json \
  --include-latency \
  --custom-metrics \
  --verbose
```

#### Evaluation Report (`evaluation_report.json`)
```json
{
  "evaluation_metadata": {
    "timestamp": "2024-01-15T14:30:00Z",
    "suite_name": "customer-support-evaluation",
    "suite_version": "1.2.0",
    "suite_hash": "sha256:abc123...",
    "total_cases": 5,
    "evaluated_cases": 5,
    "skipped_cases": 0,
    "evaluation_duration_ms": 2450
  },
  "overall_metrics": {
    "total_score": 0.92,
    "accuracy": 0.80,
    "json_schema_compliance": 1.0,
    "key_match_rate": 0.85,
    "average_latency_ms": 1526.0,
    "custom_metrics": {
      "response_time_compliance": 1.0,
      "sentiment_score_avg": 0.78
    }
  },
  "detailed_results": [
    {
      "case_id": "cs001",
      "status": "passed",
      "score": 1.0,
      "metrics": {
        "exact_match": true,
        "json_schema_valid": true,
        "key_match_rate": 1.0,
        "latency_ms": 1250,
        "custom_metrics": {
          "response_time_compliance": true,
          "sentiment_score": 0.85
        }
      },
      "details": {
        "expected": {"status":"ok","result":{"category":"returns","action":"provide_instructions"}},
        "predicted": {"status":"ok","result":{"category":"returns","action":"provide_instructions"}},
        "validation_errors": []
      }
    },
    {
      "case_id": "cs002",
      "status": "passed",
      "score": 0.9,
      "metrics": {
        "exact_match": false,
        "json_schema_valid": true,
        "key_match_rate": 0.8,
        "latency_ms": 2100,
        "custom_metrics": {
          "response_time_compliance": true,
          "sentiment_score": 0.72
        }
      },
      "details": {
        "expected": {"status":"escalate","result":{"category":"damage","action":"create_ticket"}},
        "predicted": {"status":"escalate","result":{"category":"damage","action":"create_ticket"}},
        "validation_errors": ["Minor difference in result structure"]
      }
    }
  ],
  "summary_by_tag": {
    "functional": {
      "total_cases": 5,
      "passed_cases": 5,
      "average_score": 0.92
    },
    "escalation": {
      "total_cases": 2,
      "passed_cases": 2,
      "average_score": 0.9
    },
    "common": {
      "total_cases": 2,
      "passed_cases": 2,
      "average_score": 1.0
    }
  },
  "performance_metrics": {
    "latency": {
      "min_ms": 980,
      "max_ms": 2100,
      "mean_ms": 1526.0,
      "p50_ms": 1450,
      "p95_ms": 2050,
      "p99_ms": 2100
    },
    "throughput": {
      "cases_per_second": 2.04,
      "tokens_per_second": 156.8
    }
  }
}
```

### 5. Regression Comparison

#### Compare with Baseline
```bash
toolkit-eval compare \
  --baseline baseline_evaluation.json \
  --candidate evaluation_report.json \
  --out comparison_report.json \
  --threshold 0.05 \
  --detailed
```

#### Comparison Report (`comparison_report.json`)
```json
{
  "comparison_metadata": {
    "timestamp": "2024-01-15T14:35:00Z",
    "baseline_evaluation": "2024-01-10T10:20:00Z",
    "candidate_evaluation": "2024-01-15T14:30:00Z",
    "suite_name": "customer-support-evaluation",
    "regression_threshold": 0.05
  },
  "overall_comparison": {
    "regression_detected": false,
    "improvement_detected": true,
    "score_change": 0.03,
    "score_change_percent": 3.37,
    "baseline_score": 0.89,
    "candidate_score": 0.92
  },
  "metric_comparisons": {
    "accuracy": {
      "baseline": 0.80,
      "candidate": 0.80,
      "change": 0.0,
      "change_percent": 0.0,
      "status": "stable"
    },
    "json_schema_compliance": {
      "baseline": 1.0,
      "candidate": 1.0,
      "change": 0.0,
      "change_percent": 0.0,
      "status": "stable"
    },
    "key_match_rate": {
      "baseline": 0.82,
      "candidate": 0.85,
      "change": 0.03,
      "change_percent": 3.66,
      "status": "improved"
    },
    "average_latency_ms": {
      "baseline": 1650.0,
      "candidate": 1526.0,
      "change": -124.0,
      "change_percent": -7.52,
      "status": "improved"
    }
  },
  "case_level_changes": [
    {
      "case_id": "cs002",
      "baseline_score": 0.8,
      "candidate_score": 0.9,
      "change": 0.1,
      "status": "improved"
    },
    {
      "case_id": "cs005",
      "baseline_score": 0.9,
      "candidate_score": 0.85,
      "change": -0.05,
      "status": "degraded"
    }
  ],
  "recommendations": [
    "Overall performance improved by 3.37%",
    "Latency reduced by 7.52% - good optimization",
    "Monitor case cs005 for potential regression",
    "Consider increasing test coverage for edge cases"
  ]
}
```

## Advanced Configuration

### Custom Scoring Metrics

#### Define Custom Metrics in Suite
```json
{
  "scoring": {
    "custom_metrics": [
      {
        "name": "response_length",
        "type": "range",
        "min_value": 50,
        "max_value": 500,
        "weight": 0.1
      },
      {
        "name": "sentiment_analysis",
        "type": "external",
        "endpoint": "https://api.company.com/sentiment",
        "threshold": 0.6,
        "weight": 0.2
      },
      {
        "name": "toxicity_check",
        "type": "boolean",
        "required": true,
        "weight": 0.3
      }
    ]
  }
}
```

#### External Metric Integration
```python
# custom_metrics.py
import requests
from typing import Dict, Any

class SentimentMetric:
    def __init__(self, endpoint: str, threshold: float):
        self.endpoint = endpoint
        self.threshold = threshold
    
    def evaluate(self, prediction: Dict[str, Any]) -> float:
        response = requests.post(
            self.endpoint,
            json={"text": prediction.get("response", "")}
        )
        sentiment_score = response.json()["score"]
        return 1.0 if sentiment_score >= self.threshold else 0.0

class ToxicityMetric:
    def evaluate(self, prediction: Dict[str, Any]) -> float:
        # Custom toxicity detection logic
        text = prediction.get("response", "")
        toxicity_score = self.detect_toxicity(text)
        return 1.0 if toxicity_score < 0.1 else 0.0
    
    def detect_toxicity(self, text: str) -> float:
        # Implementation here
        return 0.0
```

### CLI Configuration

#### Global Configuration (`~/.toolkit-eval/config.json`)
```json
{
  "default_settings": {
    "compression_level": 6,
    "include_assets": true,
    "verify_signatures": true,
    "regression_threshold": 0.05
  },
  "paths": {
    "suite_cache": "~/.toolkit-eval/cache",
    "key_directory": "~/.toolkit-eval/keys",
    "reports_directory": "~/.toolkit-eval/reports"
  },
  "network": {
    "timeout_seconds": 30,
    "retry_attempts": 3,
    "proxy_url": null
  },
  "logging": {
    "level": "INFO",
    "format": "json",
    "file": "~/.toolkit-eval/logs/eval.log"
  }
}
```

## Integration Examples

### CI/CD Pipeline Integration

#### GitHub Actions
```yaml
# .github/workflows/model-evaluation.yml
name: Model Evaluation

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  evaluate-model:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Install Toolkit Eval Harness
        run: pip install toolkit-eval-harness[signing]
      
      - name: Download Test Suite
        run: |
          curl -L "${{ secrets.SUITE_URL }}" -o test_suite.zip
          toolkit-eval pack verify --suite test_suite.zip
      
      - name: Generate Predictions
        run: |
          python scripts/generate_predictions.py \
            --model-path model/ \
            --test-suite test_suite.zip \
            --output predictions.jsonl
      
      - name: Run Evaluation
        run: |
          toolkit-eval run \
            --suite test_suite.zip \
            --predictions predictions.jsonl \
            --out evaluation_report.json
      
      - name: Compare with Baseline
        if: github.event_name == 'pull_request'
        run: |
          toolkit-eval compare \
            --baseline baseline/baseline_report.json \
            --candidate evaluation_report.json \
            --threshold 0.05 \
            --out comparison_report.json
      
      - name: Upload Evaluation Report
        uses: actions/upload-artifact@v3
        with:
          name: evaluation-report
          path: evaluation_report.json
      
      - name: Check for Regression
        if: github.event_name == 'pull_request'
        run: |
          if [ "$(jq -r '.overall_comparison.regression_detected' comparison_report.json)" = "true" ]; then
            echo "âŒ Regression detected!"
            jq '.recommendations[]' comparison_report.json
            exit 1
          else
            echo "âœ… No regression detected"
          fi
```

#### GitLab CI
```yaml
# .gitlab-ci.yml
stages:
  - test
  - evaluate

variables:
  EVALUATION_THRESHOLD: "0.05"

model_evaluation:
  stage: evaluate
  image: python:3.11
  before_script:
    - pip install toolkit-eval-harness
  script:
    - toolkit-eval run --suite $TEST_SUITE --predictions predictions.jsonl --out report.json
    - toolkit-eval compare --baseline baseline.json --candidate report.json --threshold $EVALUATION_THRESHOLD --out comparison.json
    - |
      if [ "$(jq -r '.overall_comparison.regression_detected' comparison.json)" = "true" ]; then
        echo "Regression detected - failing pipeline"
        exit 1
      fi
  artifacts:
    reports:
      junit: evaluation_report.xml
    paths:
      - report.json
      - comparison.json
  only:
    - merge_requests
    - main
```

### Python API Integration

```python
from toolkit_eval_harness import EvaluationRunner, SuiteManager, ComparisonEngine

# Initialize components
suite_manager = SuiteManager()
evaluator = EvaluationRunner()
comparator = ComparisonEngine()

# Load and verify test suite
suite = suite_manager.load_suite("test_suite.zip")
suite_manager.verify_suite(suite)

# Run evaluation
results = evaluator.evaluate(
    suite=suite,
    predictions_file="predictions.jsonl",
    include_latency=True,
    custom_metrics=True
)

# Save results
results.save("evaluation_report.json")

# Compare with baseline
if baseline_exists:
    baseline = EvaluationResults.load("baseline_report.json")
    comparison = comparator.compare(baseline, results, threshold=0.05)
    
    if comparison.regression_detected:
        print(f"âš ï¸  Regression detected: {comparison.score_change:.3f}")
        for rec in comparison.recommendations:
            print(f"ðŸ’¡ {rec}")
        exit(1)
    else:
        print("âœ… No regression detected")

# Integration with model training
def evaluate_model(model, test_suite_path):
    """Evaluate a trained model against test suite"""
    # Generate predictions
    predictions = []
    for case in test_suite.cases:
        prediction = model.predict(case.input)
        predictions.append({
            "id": case.id,
            "prediction": prediction,
            "latency_ms": case.latency
        })
    
    # Save predictions
    with open("predictions.jsonl", "w") as f:
        for pred in predictions:
            f.write(json.dumps(pred) + "\n")
    
    # Run evaluation
    results = evaluator.evaluate(
        suite=test_suite,
        predictions_file="predictions.jsonl"
    )
    
    return results
```

### MLflow Integration

```python
import mlflow
import mlflow.pyfunc
from toolkit_eval_harness import EvaluationRunner

def log_evaluation_to_mlflow(model_uri, test_suite_path):
    """Log evaluation results to MLflow"""
    # Load model
    model = mlflow.pyfunc.load_model(model_uri)
    
    # Generate predictions
    predictions = generate_predictions(model, test_suite_path)
    
    # Run evaluation
    evaluator = EvaluationRunner()
    results = evaluator.evaluate(
        suite=test_suite_path,
        predictions=predictions
    )
    
    # Log to MLflow
    with mlflow.start_run():
        mlflow.log_metrics({
            "accuracy": results.overall_metrics.accuracy,
            "total_score": results.overall_metrics.total_score,
            "avg_latency_ms": results.overall_metrics.average_latency_ms
        })
        
        mlflow.log_artifact("evaluation_report.json", "evaluations")
        
        # Log per-tag metrics
        for tag, metrics in results.summary_by_tag.items():
            mlflow.log_metric(f"{tag}_avg_score", metrics["average_score"])

# Usage in training pipeline
def train_and_evaluate():
    # Train model
    model = train_model()
    
    # Log model to MLflow
    with mlflow.start_run() as run:
        mlflow.pyfunc.log_model(model, "model")
        
        # Evaluate model
        log_evaluation_to_mlflow(run.info.artifact_uri + "/model", "test_suite.zip")
```

## Production Deployment

### Docker Deployment

```dockerfile
# Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install Toolkit Eval Harness
RUN pip install toolkit-eval-harness[signing]

# Copy evaluation scripts
COPY scripts/ /app/scripts/
COPY suites/ /app/suites/
COPY keys/ /app/keys/

# Create non-root user
RUN useradd -m -u 1000 evaluser && chown -R evaluser:evaluser /app
USER evaluser

# Default command
CMD ["python", "scripts/evaluate_model.py"]
```

```yaml
# docker-compose.yml
version: '3.8'
services:
  eval-harness:
    build: .
    environment:
      - EVALUATION_THRESHOLD=0.05
      - SUITE_PATH=/app/suites/customer-support.zip
      - KEY_PATH=/app/keys/eval_public.pem
    volumes:
      - ./predictions:/app/predictions
      - ./reports:/app/reports
    command: >
      sh -c "
        toolkit-eval pack verify --suite $SUITE_PATH &&
        toolkit-eval run --suite $SUITE_PATH --predictions /app/predictions/latest.jsonl --out /app/reports/latest.json &&
        toolkit-eval compare --baseline /app/reports/baseline.json --candidate /app/reports/latest.json --threshold $EVALUATION_THRESHOLD --out /app/reports/comparison.json
      "
```

### Kubernetes Deployment

```yaml
# k8s/evaluation-job.yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: model-evaluation
spec:
  template:
    spec:
      containers:
      - name: eval-harness
        image: akiva/eval-harness:latest
        env:
        - name: SUITE_URL
          valueFrom:
            secretKeyRef:
              name: evaluation-secrets
              key: suite_url
        - name: MODEL_URL
          valueFrom:
            secretKeyRef:
              name: evaluation-secrets
              key: model_url
        - name: EVALUATION_THRESHOLD
          value: "0.05"
        command:
        - /bin/bash
        - -c
        - |
          # Download test suite
          curl -L "$SUITE_URL" -o /tmp/suite.zip
          toolkit-eval pack verify --suite /tmp/suite.zip
          
          # Generate predictions
          python scripts/generate_predictions.py --model-url "$MODEL_URL" --suite /tmp/suite.zip --output /tmp/predictions.jsonl
          
          # Run evaluation
          toolkit-eval run --suite /tmp/suite.zip --predictions /tmp/predictions.jsonl --out /tmp/report.json
          
          # Upload results
          curl -X POST -F "file=@/tmp/report.json" "${RESULTS_ENDPOINT}/upload"
        resources:
          requests:
            cpu: 500m
            memory: 1Gi
          limits:
            cpu: 2000m
            memory: 4Gi
      restartPolicy: Never
```

## Monitoring and Observability

### Prometheus Metrics

```python
# metrics.py
from prometheus_client import Counter, Histogram, Gauge
import time

# Define metrics
EVALUATION_COUNTER = Counter('evaluations_total', 'Total evaluations', ['status'])
EVALUATION_DURATION = Histogram('evaluation_duration_seconds', 'Evaluation duration')
MODEL_SCORE_GAUGE = Gauge('model_score', 'Latest model score')
REGRESSION_COUNTER = Counter('regressions_detected_total', 'Total regressions detected')

def evaluate_with_metrics(suite_path, predictions_path):
    start_time = time.time()
    
    try:
        results = evaluator.evaluate(suite_path, predictions_path)
        
        # Update metrics
        EVALUATION_COUNTER.labels(status='success').inc()
        EVALUATION_DURATION.observe(time.time() - start_time)
        MODEL_SCORE_GAUGE.set(results.overall_metrics.total_score)
        
        return results
        
    except Exception as e:
        EVALUATION_COUNTER.labels(status='error').inc()
        raise e

def check_regression_with_metrics(baseline_path, candidate_path, threshold):
    comparison = comparator.compare(baseline_path, candidate_path, threshold)
    
    if comparison.regression_detected:
        REGRESSION_COUNTER.inc()
    
    return comparison
```

### Grafana Dashboard

```json
{
  "dashboard": {
    "title": "Model Evaluation Dashboard",
    "panels": [
      {
        "title": "Evaluation Success Rate",
        "type": "stat",
        "targets": [
          {
            "expr": "rate(evaluations_total{status=\"success\"}[5m]) / rate(evaluations_total[5m])"
          }
        ]
      },
      {
        "title": "Model Score Trend",
        "type": "graph",
        "targets": [
          {
            "expr": "model_score"
          }
        ]
      },
      {
        "title": "Regression Detection",
        "type": "singlestat",
        "targets": [
          {
            "expr": "increase(regressions_detected_total[1h])"
          }
        ]
      }
    ]
  }
}
```

## Best Practices

### Test Suite Design
1. **Comprehensive Coverage**: Include functional, edge case, and negative test cases
2. **Version Control**: Use semantic versioning for test suites
3. **Documentation**: Clear descriptions and expected behaviors
4. **Regular Updates**: Keep suites current with evolving requirements

### Evaluation Strategy
1. **Baseline Management**: Maintain stable baseline evaluations
2. **Threshold Setting**: Use statistically significant regression thresholds
3. **Metric Selection**: Choose metrics aligned with business objectives
4. **Continuous Monitoring**: Track evaluation trends over time

### CI/CD Integration
1. **Early Detection**: Evaluate models as early as possible in pipelines
2. **Fail Fast**: Configure pipelines to fail on significant regressions
3. **Parallel Execution**: Run multiple evaluations in parallel for efficiency
4. **Artifact Management**: Store evaluation results with proper versioning

## Troubleshooting

### Common Issues

#### Suite Verification Fails
```bash
# Check suite integrity
toolkit-eval pack verify --suite test_suite.zip --verbose

# Re-create pack if corrupted
toolkit-eval pack create --suite-dir suite_dir --out test_suite.zip --force
```

#### Evaluation Performance Issues
```bash
# Use sample evaluation for large suites
toolkit-eval run --suite test_suite.zip --predictions predictions.jsonl --sample-size 1000

# Parallel processing
export Toolkit_EVAL_WORKERS=4
toolkit-eval run --suite test_suite.zip --predictions predictions.jsonl --parallel
```

#### Regression Detection Issues
```bash
# Adjust threshold
toolkit-eval compare --baseline baseline.json --candidate report.json --threshold 0.1

# Detailed comparison
toolkit-eval compare --baseline baseline.json --candidate report.json --detailed --per-case
```

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

### Development Setup

```bash
# Clone repository
git clone https://github.com/<org>/eval-harness.git
cd eval-harness

# Install development dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run linting
ruff check .
black .

# Run type checking
mypy .
```

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Support

- **Documentation**: [Full documentation](https://<docs-url>/eval-harness)
- **Issues**: [GitHub Issues](https://github.com/<org>/eval-harness/issues)
- **Community**: [Discord Server](https://discord.gg/akiva)
- **Email**: <support-email>

---

**Toolkit Eval Harness** - Comprehensive model evaluation with confidence and reliability.

Built with â¤ï¸ by the Toolkit team.



