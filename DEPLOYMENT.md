# Toolkit Eval Harness - Deployment Guide

## ðŸš€ Quick Start

### Prerequisites
- Python 3.9+
- Docker & Docker Compose (optional)

### Option 1: Docker Deployment (Recommended)

```bash
# Navigate to directory
cd eval-harness

# Build image
docker-compose build

# Create suite pack
docker-compose run --rm pack-create

# Run evaluation
docker-compose run --rm eval-run

# Check regression
docker-compose run --rm regression-check

# Interactive shell
docker-compose run --rm eval-harness bash
```

### Option 2: Local Installation

```bash
# Install from source
pip install -e ".[dev]"

# Verify installation
toolkit-eval --version

# Run tests
pytest
```

## ðŸ”§ Configuration

### Environment Variables

See `.env.example` for all options.

**Key Settings:**
- `DEFAULT_SCORER`: Scoring method (exact_match, json_schema, custom)
- `PARALLEL_WORKERS`: Number of parallel evaluation workers
- `REGRESSION_THRESHOLD`: Sensitivity for regression detection
- `ENABLE_SIGNING`: Enable cryptographic signing of suite packs

### CLI Usage

```bash
# Create suite pack
toolkit-eval pack create \
  --suite-dir suites/my-suite \
  --out packs/my-suite.zip

# Verify pack
toolkit-eval pack verify \
  --suite packs/my-suite.zip

# Run evaluation
toolkit-eval run \
  --suite packs/my-suite.zip \
  --predictions predictions.jsonl \
  --out results.json

# Check regression
toolkit-eval regression \
  --current results.json \
  --baseline baseline.json \
  --threshold 0.05
```

## ðŸ“Š Production Deployment

### 1. CI/CD Integration

**GitHub Actions Example:**
```yaml
- name: Run Evaluation
  run: |
    toolkit-eval run \
      --suite packs/production-suite.zip \
      --predictions predictions.jsonl \
      --out results.json
    
    toolkit-eval regression \
      --current results.json \
      --baseline baseline.json \
      --fail-on-regression
```

**Exit Codes:**
- `0`: All tests passed, no regression
- `1`: Tests failed or regression detected
- `2`: Error in execution

### 2. Suite Pack Management

```bash
# Version your suite packs
toolkit-eval pack create \
  --suite-dir suites/v1.0.0 \
  --out packs/suite-v1.0.0.zip \
  --sign

# Verify integrity
toolkit-eval pack verify \
  --suite packs/suite-v1.0.0.zip \
  --verify-signature
```

### 3. Monitoring Integration

```python
from toolkit_eval_harness.monitoring import get_health_status

# Check system health
status = get_health_status()
print(status)

# Check specific suite pack
from pathlib import Path
status = get_health_status(pack_path=Path("packs/suite.zip"))
```

## ðŸ”’ Security

### 1. Suite Pack Signing
```bash
# Generate signing key
toolkit-eval keys generate --out signing.key

# Sign suite pack
toolkit-eval pack create \
  --suite-dir suites/my-suite \
  --out packs/my-suite.zip \
  --sign \
  --key signing.key

# Verify signature
toolkit-eval pack verify \
  --suite packs/my-suite.zip \
  --verify-signature \
  --key signing.pub
```

### 2. Access Control
- Store suite packs in secure storage
- Use signed packs for production
- Verify signatures before evaluation
- Audit all evaluation runs

## ðŸ“ˆ Best Practices

### 1. Suite Management
- Version suite packs with semantic versioning
- Store packs in version control or artifact storage
- Sign packs for production use
- Document test case changes

### 2. Evaluation
- Run evaluations in isolated environments
- Use deterministic scorers
- Save detailed results for debugging
- Track evaluation history

### 3. Regression Detection
- Set appropriate thresholds
- Compare against stable baselines
- Investigate regressions before deployment
- Update baselines periodically

## ðŸ› Troubleshooting

### Common Issues

**Pack Creation Fails:**
```bash
# Ensure suite directory structure is correct
ls -la suites/my-suite/

# Check suite.json format
cat suites/my-suite/suite.json | jq .
```

**Evaluation Fails:**
```bash
# Verify predictions format
cat predictions.jsonl | jq -c .

# Check scorer configuration
toolkit-eval run --scorer exact_match --verbose
```

**Regression Always Detected:**
```bash
# Lower threshold
toolkit-eval regression --threshold 0.1

# Check baseline results
cat baseline.json | jq .
```

## ðŸ“ž Support

- Documentation: [README.md](README.md)
- Examples: [examples/](examples/)
- Issues: GitHub Issues
- Email: <support-email>




