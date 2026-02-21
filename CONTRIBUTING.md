# Contributing

## Dev setup

```bash
pip install -e ".[dev]"
pytest -q
```

## Quality gates

- `ruff check .`
- `ruff format .`
- `pyright`
- `pytest -q`

