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
ruff check .           # Lint (rules: E, F, I, B, UP); CI runs this
pyright src/           # Static type checking
pytest -x -q           # Tests (must pass, no regressions); CI runs this with coverage
```

## Running Tests

```bash
# Quick run
pytest -x -q

# With coverage report
pytest --cov=src --cov-report=term-missing --cov-fail-under=80

# Single test file
pytest tests/test_cli.py -v
```

Coverage threshold is 80%. Do not submit changes that drop coverage below this.

## Project Layout

See [docs/CODEBASE_MAP.md](docs/CODEBASE_MAP.md).

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

A registered scorer only runs for suites that list it in `scoring.scorers`, and like every
required scorer it must return 1.0 for the case to pass:

```json
{"name": "my-suite", "scoring": {"scorers": ["contains_match"]}}
```

Return a score in [0, 1]. A scorer that raises or returns anything else fails the case.

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

This lists the registered plugin scorers under the `registered_scorers` key. The built-in
`exact`, `json` and configurable scorers (`normalized_exact`, `token_f1`, `fuzzy`, `regex`,
`numeric`, `json_schema`, `embedding`, `llm_judge`) are not listed there; see the README
"Built-in scorers" section. Their names take precedence over plugins with the same name.

## Commit Messages

- Use present tense ("Add feature" not "Added feature")
- Keep the first line under 72 characters
- Reference issue numbers where applicable

## Reporting Issues

Open an issue at https://github.com/AKIVA-AI/toolkit-eval-harness/issues with:
- Steps to reproduce
- Expected vs actual behavior
- Python version and OS

## Conduct, security and license

- Everyone taking part follows the [Code of Conduct](CODE_OF_CONDUCT.md).
- Report security problems privately as described in [SECURITY.md](SECURITY.md),
  not in a public issue.
- Contributions are accepted under the Apache License 2.0 ([LICENSE](LICENSE)):
  by opening a pull request you agree that your contribution is licensed under
  it, as section 5 of the license describes.
- Maintainers: releases are described in [RELEASING.md](RELEASING.md).
