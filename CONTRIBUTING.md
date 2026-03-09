# Contributing to Toolkit Eval Harness

## Development Setup

1. **Clone the repository:**

   ```bash
   git clone https://github.com/AKIVA-AI/toolkit-eval-harness.git
   cd toolkit-eval-harness
   ```

2. **Create a virtual environment (recommended):**

   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Linux/macOS
   .venv\Scripts\activate     # Windows
   ```

3. **Install in editable mode with dev dependencies:**

   ```bash
   pip install -e ".[dev]"
   ```

4. **Install pre-commit hooks:**

   ```bash
   pip install pre-commit
   pre-commit install
   ```

## Quality Gates

All of the following must pass before merging:

```bash
ruff check .           # Lint (rules: E, F, I, B, UP)
ruff format --check .  # Format check
pyright                # Static type checking
pytest -x -q           # Tests (must pass, no regressions)
```

## Running Tests

```bash
# Quick run
pytest -x -q

# With coverage report
pytest --cov=src --cov-report=term-missing --cov-fail-under=70

# Single test file
pytest tests/test_cli.py -v
```

Coverage threshold is 70%. Do not submit changes that drop coverage below this.

## Project Layout

```
src/toolkit_eval_harness/
  __init__.py       # Public API exports
  cli.py            # CLI entry point and subcommands
  compare.py        # Report comparison / regression detection
  formatters.py     # Output formatters (JSON, table, CSV)
  hashing.py        # SHA-256 file hashing
  io.py             # File I/O utilities with path validation
  logging_config.py # Structured logging setup
  pack.py           # Suite pack (ZIP) create / verify / extract
  plugins.py        # Scorer plugin system
  report.py         # EvalReport dataclass
  runner.py         # Suite execution engine
  scoring.py        # Built-in scorers (exact_match, json_required_keys)
  signing.py        # Ed25519 signing / verification
  suite.py          # EvalSuite / EvalCase dataclasses
tests/
  conftest.py       # Test configuration (adds src/ to path)
  test_*.py         # Test modules
```

## Writing Custom Scorers (Plugin System)

You can extend the eval harness with custom scoring functions.

### Option 1: Programmatic Registration

```python
from toolkit_eval_harness.plugins import register_scorer

def contains_scorer(*, expected, predicted, **kwargs):
    """Score 1.0 if expected text appears in prediction."""
    if predicted and str(expected) in str(predicted):
        return 1.0, {"contains": True}
    return 0.0, {"contains": False}

register_scorer("contains_match", contains_scorer)
```

### Option 2: Entry Points (for installable packages)

In your package's `pyproject.toml`:

```toml
[project.entry-points."toolkit_eval_harness.scorers"]
my_scorer = "my_package.scoring:my_scorer_func"
```

The function must have the signature:

```python
def my_scorer_func(*, expected: Any, predicted: Any, **kwargs) -> tuple[float, dict[str, Any]]:
    ...
```

### Listing Available Scorers

```bash
toolkit-eval check-deps
```

This reports all registered scorers (built-in + plugins) under the `registered_scorers` key.

## Commit Messages

- Use present tense ("Add feature" not "Added feature")
- Keep the first line under 72 characters
- Reference issue numbers where applicable

## Reporting Issues

Open an issue at https://github.com/AKIVA-AI/toolkit-eval-harness/issues with:
- Steps to reproduce
- Expected vs actual behavior
- Python version and OS
