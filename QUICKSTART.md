# Toolkit Eval Harness - Quick Start

Get started with model evaluation in 5 minutes!

## ðŸš€ Installation

```bash
# Install
pip install -e ".[dev]"

# Verify
toolkit-eval --version
```

## ðŸ“ Basic Workflow

### 1. Create Test Suite

Create `suites/my-suite/suite.json`:
```json
{
  "name": "sentiment-analysis-v1",
  "version": "1.0.0",
  "test_cases": [
    {
      "id": "test_001",
      "input": {"text": "I love this!"},
      "expected_output": {"sentiment": "positive"},
      "tags": ["positive"]
    }
  ]
}
```

### 2. Create Suite Pack

```bash
toolkit-eval pack create \
  --suite-dir suites/my-suite \
  --out packs/my-suite.zip
```

### 3. Generate Predictions

Create `predictions.jsonl`:
```json
{"id": "test_001", "output": {"sentiment": "positive"}}
```

### 4. Run Evaluation

```bash
toolkit-eval run \
  --suite packs/my-suite.zip \
  --predictions predictions.jsonl \
  --out results.json
```

**Output:**
```
âœ“ All tests passed
  Total: 1
  Passed: 1
  Accuracy: 100%
```

## ðŸŽ¯ Common Use Cases

### Model Regression Testing

```bash
# Run evaluation
toolkit-eval run \
  --suite packs/production-suite.zip \
  --predictions current_predictions.jsonl \
  --out current_results.json

# Check for regression
toolkit-eval regression \
  --current current_results.json \
  --baseline baseline_results.json \
  --threshold 0.05
```

### CI/CD Integration

```yaml
# .github/workflows/eval.yml
- name: Run Evaluation
  run: |
    toolkit-eval run \
      --suite packs/suite.zip \
      --predictions predictions.jsonl \
      --out results.json
    
    toolkit-eval regression \
      --current results.json \
      --baseline baseline.json
```

### Batch Evaluation

```bash
# Evaluate multiple models
for model in model_v1 model_v2 model_v3; do
  toolkit-eval run \
    --suite packs/suite.zip \
    --predictions ${model}_predictions.jsonl \
    --out ${model}_results.json
done
```

## ðŸ³ Docker Usage

```bash
# Build
docker-compose build

# Create pack
docker-compose run --rm pack-create

# Run evaluation
docker-compose run --rm eval-run

# Check regression
docker-compose run --rm regression-check
```

## ðŸ§ª Run Examples

```bash
# Basic evaluation example
python examples/basic_evaluation.py
```

## ðŸ’¡ Tips

1. **Version Suite Packs**: Use semantic versioning
2. **Sign Packs**: Enable signing for production
3. **Deterministic Scoring**: Use consistent scorers
4. **Track History**: Save all evaluation results
5. **Automate Checks**: Integrate into CI/CD

## ðŸ“š Next Steps

- Read [README.md](README.md) for detailed documentation
- Check [DEPLOYMENT.md](DEPLOYMENT.md) for production setup
- Explore [examples/](examples/) for more use cases
- Review [tests/](tests/) for implementation patterns

## ðŸ†˜ Need Help?

- Full docs: [README.md](README.md)
- Deployment: [DEPLOYMENT.md](DEPLOYMENT.md)
- Support: <support-email>

---

**Ready to evaluate your models? Start testing now!** ðŸš€




