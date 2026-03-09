"""Plugin system for custom scorers.

Scorers can be registered in two ways:

1. **Programmatic registration** -- call ``register_scorer()`` at import time::

       from toolkit_eval_harness.plugins import register_scorer

       def my_scorer(*, expected, predicted, **kwargs):
           score = 1.0 if predicted and expected in str(predicted) else 0.0
           return score, {"contains": score == 1.0}

       register_scorer("contains_match", my_scorer)

2. **Entry-point discovery** -- declare a ``toolkit_eval_harness.scorers``
   entry point in your package's ``pyproject.toml``::

       [project.entry-points."toolkit_eval_harness.scorers"]
       my_scorer = "my_package.scoring:my_scorer_func"

   The entry point value must be a callable with the signature::

       (*, expected: Any, predicted: Any, **kwargs) -> tuple[float, dict[str, Any]]

Both approaches populate the same global registry which ``run_suite`` consults
when a case's scoring method is not one of the built-in scorers.
"""

from __future__ import annotations

import logging
from importlib.metadata import entry_points
from typing import Any, Protocol

logger = logging.getLogger(__name__)

ENTRY_POINT_GROUP = "toolkit_eval_harness.scorers"


class ScorerFunc(Protocol):
    """Protocol that all scorer callables must satisfy."""

    def __call__(
        self, *, expected: Any, predicted: Any, **kwargs: Any,
    ) -> tuple[float, dict[str, Any]]:
        ...


# ---------------------------------------------------------------------------
# Global registry
# ---------------------------------------------------------------------------

_registry: dict[str, ScorerFunc] = {}
_entry_points_loaded = False


def register_scorer(name: str, func: ScorerFunc) -> None:
    """Register a scorer function under *name*.

    Args:
        name: Unique scorer name (e.g. ``"bleu"``).
        func: Callable with signature ``(*, expected, predicted, **kw) -> (float, dict)``.

    Raises:
        ValueError: If *name* is already registered.
        TypeError: If *func* is not callable.
    """
    if not callable(func):
        raise TypeError(
            f"Scorer '{name}' is not callable. "
            f"Expected a function with signature (*, expected, predicted, **kw) -> (float, dict), "
            f"got {type(func).__name__}."
        )
    if name in _registry:
        raise ValueError(
            f"Scorer '{name}' is already registered. "
            "Use a unique name or call unregister_scorer() first."
        )
    _registry[name] = func
    logger.debug("Registered scorer: %s", name)


def unregister_scorer(name: str) -> None:
    """Remove a previously registered scorer.

    Args:
        name: Scorer name to remove.

    Raises:
        KeyError: If *name* is not registered.
    """
    if name not in _registry:
        raise KeyError(
            f"Scorer '{name}' is not registered. "
            f"Available scorers: {', '.join(sorted(_registry)) or '(none)'}."
        )
    del _registry[name]
    logger.debug("Unregistered scorer: %s", name)


def get_scorer(name: str) -> ScorerFunc:
    """Return the scorer registered under *name*.

    Loads entry-point scorers on first call.

    Args:
        name: Scorer name to look up.

    Returns:
        The scorer callable.

    Raises:
        KeyError: If *name* is not found in the registry or entry points.
    """
    _load_entry_points()
    if name not in _registry:
        available = ", ".join(sorted(_registry)) or "(none)"
        raise KeyError(
            f"Scorer '{name}' not found. "
            f"Available scorers: {available}. "
            f"Register a custom scorer with register_scorer() or install a plugin "
            f"that provides a '{ENTRY_POINT_GROUP}' entry point."
        )
    return _registry[name]


def list_scorers() -> list[str]:
    """Return sorted list of all registered scorer names.

    Loads entry-point scorers on first call.
    """
    _load_entry_points()
    return sorted(_registry)


def _load_entry_points() -> None:
    """Discover and register scorers from installed entry points (once)."""
    global _entry_points_loaded
    if _entry_points_loaded:
        return
    _entry_points_loaded = True

    try:
        eps = entry_points(group=ENTRY_POINT_GROUP)
    except TypeError:
        # Python 3.9 compat (unlikely given >=3.10 requirement, but safe)
        eps = entry_points().get(ENTRY_POINT_GROUP, [])  # type: ignore[assignment,call-overload]

    for ep in eps:
        try:
            func = ep.load()
            if ep.name not in _registry:
                _registry[ep.name] = func
                logger.info("Loaded scorer plugin: %s (from %s)", ep.name, ep.value)
        except Exception:
            logger.warning("Failed to load scorer plugin: %s", ep.name, exc_info=True)


def _reset_registry() -> None:
    """Clear registry and reset entry-point flag. For testing only."""
    global _entry_points_loaded
    _registry.clear()
    _entry_points_loaded = False
