"""Tests for the scorer plugin system."""

from __future__ import annotations

from typing import Any

import pytest

from toolkit_eval_harness.plugins import (
    _reset_registry,
    get_scorer,
    list_scorers,
    register_scorer,
    unregister_scorer,
)


@pytest.fixture(autouse=True)
def _clean_registry() -> Any:
    """Reset the plugin registry before and after each test."""
    _reset_registry()
    yield
    _reset_registry()


# ---------------------------------------------------------------------------
# register / unregister
# ---------------------------------------------------------------------------


def _dummy_scorer(*, expected: Any, predicted: Any, **kwargs: Any) -> tuple[float, dict[str, Any]]:
    return (1.0 if expected == predicted else 0.0), {"match": expected == predicted}


def test_register_and_get() -> None:
    register_scorer("dummy", _dummy_scorer)
    scorer = get_scorer("dummy")
    score, meta = scorer(expected="a", predicted="a")
    assert score == 1.0
    assert meta["match"] is True


def test_register_duplicate_raises() -> None:
    register_scorer("dup", _dummy_scorer)
    with pytest.raises(ValueError, match="already registered"):
        register_scorer("dup", _dummy_scorer)


def test_register_non_callable_raises() -> None:
    with pytest.raises(TypeError, match="not callable"):
        register_scorer("bad", "not_a_function")  # type: ignore[arg-type]


def test_unregister() -> None:
    register_scorer("temp", _dummy_scorer)
    assert "temp" in list_scorers()
    unregister_scorer("temp")
    assert "temp" not in list_scorers()


def test_unregister_missing_raises() -> None:
    with pytest.raises(KeyError, match="not registered"):
        unregister_scorer("nonexistent")


def test_get_missing_raises() -> None:
    with pytest.raises(KeyError, match="not found"):
        get_scorer("nonexistent")


# ---------------------------------------------------------------------------
# list_scorers
# ---------------------------------------------------------------------------


def test_list_scorers_empty() -> None:
    assert list_scorers() == []


def test_list_scorers_sorted() -> None:
    register_scorer("zebra", _dummy_scorer)
    register_scorer("alpha", _dummy_scorer)
    assert list_scorers() == ["alpha", "zebra"]


# ---------------------------------------------------------------------------
# Scorer contract
# ---------------------------------------------------------------------------


def test_scorer_returns_tuple() -> None:
    """A scorer must return (float, dict)."""
    register_scorer("contract", _dummy_scorer)
    result = get_scorer("contract")(expected="x", predicted="y")
    assert isinstance(result, tuple)
    assert len(result) == 2
    assert isinstance(result[0], float)
    assert isinstance(result[1], dict)
