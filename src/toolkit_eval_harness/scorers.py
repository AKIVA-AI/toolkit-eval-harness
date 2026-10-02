"""Built-in configurable scorers.

A suite enables them in ``scoring.scorers``, either by name (``"normalized_exact"``) or as an
object with options (``{"name": "fuzzy", "threshold": 0.9}``). Every scorer returns a score
in [0, 1] and a metadata dict. Thresholded scorers return 1.0 when the metric reaches the
threshold and the raw metric otherwise, so "passed" keeps meaning "every scorer returned 1.0".

- ``normalized_exact``: the SQuAD-normalized prediction equals the (or any) expected answer.
  Reference: SQuAD v1.1 ``evaluate-v1.1.py`` (``normalize_answer``, ``exact_match_score``).
- ``token_f1``: SQuAD token F1 >= ``threshold`` (default 1.0). Reference: SQuAD v1.1
  ``f1_score``.
- ``fuzzy``: Levenshtein similarity ``1 - distance / max(len)`` >= ``threshold`` (default
  0.9), as ``rapidfuzz.distance.Levenshtein.normalized_similarity``.
- ``regex``: ``re.search`` (or ``fullmatch``) of ``pattern``, or of ``expected``.
- ``numeric``: ``math.isclose(prediction, expected, rel_tol, abs_tol)`` (PEP 485).
- ``json_schema``: the prediction is valid against ``schema`` (``jsonschema`` extra).
- ``embedding``: cosine similarity of embeddings >= ``threshold`` (default 0.8); LiteLLM.
- ``llm_judge``: judge score >= ``threshold`` (default 1.0); LiteLLM (``judge`` extra).

``embedding`` and ``llm_judge`` call a model over the network. They are **off by default**:
a suite that lists them is rejected unless the run opts in (``run_suite(...,
allow_network_scorers=True)`` / ``toolkit-eval run --allow-network-scorers``). The judge's
model, prompt template and every rendered prompt and raw reply are recorded in the report.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import string
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

# A configured scorer: (expected, predicted, case_input) -> (score, metadata)
BoundScorer = Callable[[Any, Any, Any], tuple[float, dict[str, Any]]]


@dataclass(frozen=True)
class BuiltinScorer:
    name: str
    build: Callable[[dict[str, Any]], BoundScorer]
    network: bool = False
    options: tuple[str, ...] = field(default_factory=tuple)


def _threshold(options: dict[str, Any], default: float) -> float:
    value = options.get("threshold", default)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
        raise ValueError(
            f"invalid_scorer_option:threshold must be a number in [0, 1], got {value!r}"
        )
    return float(value)


def _thresholded(metric: float, threshold: float, meta: dict[str, Any]) -> tuple[float, dict]:
    meta = {**meta, "metric": metric, "threshold": threshold}
    return (1.0 if metric >= threshold else metric), meta


def _answers(expected: Any) -> list[str]:
    if isinstance(expected, list):
        return [str(e) for e in expected]
    return [str(expected)]


def _text(value: Any) -> str:
    return "" if value is None else str(value)


# ---------------------------------------------------------------------------
# SQuAD normalization, exact match and token F1
# ---------------------------------------------------------------------------

_ARTICLES = re.compile(r"\b(a|an|the)\b")
_PUNCT = set(string.punctuation)


def normalize_answer(text: str) -> str:
    """SQuAD v1.1 normalization: lower-case, drop punctuation and articles, squash spaces."""
    text = text.lower()
    text = "".join(ch for ch in text if ch not in _PUNCT)
    text = _ARTICLES.sub(" ", text)
    return " ".join(text.split())


def token_f1(prediction: str, truth: str) -> float:
    """SQuAD v1.1 token-level F1 between normalized *prediction* and *truth*."""
    pred_tokens = normalize_answer(prediction).split()
    truth_tokens = normalize_answer(truth).split()
    common = Counter(pred_tokens) & Counter(truth_tokens)
    same = sum(common.values())
    if same == 0:
        return 0.0
    precision = same / len(pred_tokens)
    recall = same / len(truth_tokens)
    return 2 * precision * recall / (precision + recall)


def _build_normalized_exact(options: dict[str, Any]) -> BoundScorer:
    def score(expected: Any, predicted: Any, _input: Any) -> tuple[float, dict[str, Any]]:
        pred = normalize_answer(_text(predicted))
        match = any(pred == normalize_answer(a) for a in _answers(expected))
        return (1.0 if match else 0.0), {"match": match, "normalized": pred}

    return score


def _build_token_f1(options: dict[str, Any]) -> BoundScorer:
    threshold = _threshold(options, 1.0)

    def score(expected: Any, predicted: Any, _input: Any) -> tuple[float, dict[str, Any]]:
        best = max(token_f1(_text(predicted), a) for a in _answers(expected))
        return _thresholded(best, threshold, {})

    return score


# ---------------------------------------------------------------------------
# Levenshtein similarity
# ---------------------------------------------------------------------------


def levenshtein(a: str, b: str) -> int:
    """Edit distance with unit costs for insert, delete and substitute (Wagner-Fischer)."""
    if len(a) < len(b):
        a, b = b, a
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        for j, cb in enumerate(b, start=1):
            current.append(
                min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb))
            )
        previous = current
    return previous[-1]


def levenshtein_similarity(a: str, b: str) -> float:
    """``1 - distance / max(len(a), len(b))``; 1.0 for two empty strings."""
    longest = max(len(a), len(b))
    return 1.0 if longest == 0 else 1.0 - levenshtein(a, b) / longest


def _build_fuzzy(options: dict[str, Any]) -> BoundScorer:
    threshold = _threshold(options, 0.9)
    normalize = options.get("normalize", "basic")
    if normalize not in ("basic", "squad", "none"):
        raise ValueError("invalid_scorer_option:fuzzy normalize must be basic, squad or none")

    def norm(text: str) -> str:
        if normalize == "squad":
            return normalize_answer(text)
        if normalize == "basic":
            return " ".join(text.lower().split())
        return text

    def score(expected: Any, predicted: Any, _input: Any) -> tuple[float, dict[str, Any]]:
        pred = norm(_text(predicted))
        best = max(levenshtein_similarity(pred, norm(a)) for a in _answers(expected))
        return _thresholded(best, threshold, {})

    return score


# ---------------------------------------------------------------------------
# regex
# ---------------------------------------------------------------------------


def _build_regex(options: dict[str, Any]) -> BoundScorer:
    mode = options.get("mode", "search")
    if mode not in ("search", "fullmatch"):
        raise ValueError("invalid_scorer_option:regex mode must be search or fullmatch")
    flags = re.IGNORECASE if options.get("ignore_case") else 0
    fixed = options.get("pattern")
    compiled = None
    if fixed is not None:
        try:
            compiled = re.compile(str(fixed), flags)
        except re.error as exc:
            raise ValueError(f"invalid_scorer_option:regex pattern: {exc}") from exc

    def score(expected: Any, predicted: Any, _input: Any) -> tuple[float, dict[str, Any]]:
        pattern = compiled or re.compile(_text(expected), flags)
        matcher = pattern.fullmatch if mode == "fullmatch" else pattern.search
        found = matcher(_text(predicted)) is not None
        return (1.0 if found else 0.0), {"match": found, "pattern": pattern.pattern}

    return score


# ---------------------------------------------------------------------------
# numeric
# ---------------------------------------------------------------------------

_NUMBER = re.compile(r"[-+]?(?:\d[\d,_]*)?\.?\d+(?:[eE][-+]?\d+)?")


def parse_number(value: Any, extract: str = "full") -> float | None:
    """Parse a number from *value*.

    ``full``: the whole (stripped) string must be a number; thousands separators ``,`` and
    ``_`` are allowed. ``first`` / ``last``: the first / last number found in the text (for
    answers such as "... so the answer is 42").
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        f = float(value)
        return f if math.isfinite(f) else None
    text = _text(value).strip()
    if extract == "full":
        candidates = [text] if _NUMBER.fullmatch(text) else []
    else:
        candidates = _NUMBER.findall(text)
    if not candidates:
        return None
    raw = candidates[0] if extract in ("full", "first") else candidates[-1]
    try:
        f = float(raw.replace(",", "").replace("_", ""))
    except ValueError:
        return None
    return f if math.isfinite(f) else None


def _build_numeric(options: dict[str, Any]) -> BoundScorer:
    extract = options.get("extract", "full")
    if extract not in ("full", "first", "last"):
        raise ValueError("invalid_scorer_option:numeric extract must be full, first or last")
    try:
        abs_tol = float(options.get("abs_tol", 0.0))
        rel_tol = float(options.get("rel_tol", 1e-9))
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid_scorer_option:numeric tolerances must be numbers") from exc
    if abs_tol < 0 or rel_tol < 0:
        raise ValueError("invalid_scorer_option:numeric tolerances must be >= 0")

    def score(expected: Any, predicted: Any, _input: Any) -> tuple[float, dict[str, Any]]:
        want = parse_number(expected, "full")
        got = parse_number(predicted, extract)
        if want is None:
            raise ValueError(f"numeric scorer: expected value {expected!r} is not a number")
        if got is None:
            return 0.0, {"match": False, "parsed": None}
        ok = math.isclose(got, want, rel_tol=rel_tol, abs_tol=abs_tol)
        return (1.0 if ok else 0.0), {"match": ok, "parsed": got, "expected": want}

    return score


# ---------------------------------------------------------------------------
# JSON Schema
# ---------------------------------------------------------------------------


def _build_json_schema(options: dict[str, Any]) -> BoundScorer:
    schema = options.get("schema")
    if not isinstance(schema, dict):
        raise ValueError("invalid_scorer_option:json_schema needs a 'schema' object")
    try:
        from jsonschema import exceptions as js_exceptions  # type: ignore[import-untyped]
        from jsonschema import validators as js_validators  # type: ignore[import-untyped]
    except ImportError as exc:
        raise ValueError(
            "missing_dependency:the json_schema scorer needs jsonschema; install "
            "'toolkit-eval-harness[jsonschema]'"
        ) from exc
    cls = js_validators.validator_for(schema)
    try:
        cls.check_schema(schema)
    except js_exceptions.SchemaError as exc:
        raise ValueError(f"invalid_scorer_option:json_schema schema: {exc.message}") from exc
    validator = cls(schema, format_checker=cls.FORMAT_CHECKER)

    def score(expected: Any, predicted: Any, _input: Any) -> tuple[float, dict[str, Any]]:
        instance = predicted
        if isinstance(predicted, str):
            try:
                instance = json.loads(predicted)
            except json.JSONDecodeError:
                return 0.0, {"valid": False, "errors": ["invalid JSON"]}
        errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.path))
        messages = [e.message for e in errors[:5]]
        return (0.0 if errors else 1.0), {"valid": not errors, "errors": messages}

    return score


# ---------------------------------------------------------------------------
# Network scorers (LiteLLM, optional)
# ---------------------------------------------------------------------------


def _litellm() -> Any:
    try:
        import litellm  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ValueError(
            "missing_dependency:embedding and llm_judge scorers need LiteLLM; install "
            "'toolkit-eval-harness[judge]'"
        ) from exc
    return litellm


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        raise ValueError("cosine similarity needs two non-empty vectors of equal length")
    dot = math.fsum(x * y for x, y in zip(a, b, strict=True))
    norm = math.sqrt(math.fsum(x * x for x in a)) * math.sqrt(math.fsum(y * y for y in b))
    return 0.0 if norm == 0 else dot / norm


def _get(obj: Any, key: str) -> Any:
    return obj[key] if isinstance(obj, dict) else getattr(obj, key)


def _build_embedding(options: dict[str, Any]) -> BoundScorer:
    model = options.get("model")
    if not model:
        raise ValueError("invalid_scorer_option:embedding needs a 'model'")
    threshold = _threshold(options, 0.8)
    litellm = _litellm()

    def score(expected: Any, predicted: Any, _input: Any) -> tuple[float, dict[str, Any]]:
        resp = litellm.embedding(model=model, input=[_text(expected), _text(predicted)])
        data = _get(resp, "data")
        vectors = [list(_get(item, "embedding")) for item in data]
        sim = max(0.0, min(1.0, cosine_similarity(vectors[0], vectors[1])))
        return _thresholded(sim, threshold, {"model": model})

    return score


DEFAULT_JUDGE_PROMPT = """You are grading an answer against a reference.

Question:
{input}

Reference answer:
{expected}

Answer to grade:
{prediction}

Rubric:
{rubric}

Reply with only a JSON object: {{"score": <number from 0 to 1>, "reason": "<one sentence>"}}"""

DEFAULT_RUBRIC = (
    "Score 1 if the answer is correct and consistent with the reference, 0 if it is wrong or "
    "contradicts the reference, and a value in between for partially correct answers."
)

_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)


def judge_prompt_sha256(template: str) -> str:
    return hashlib.sha256(template.encode("utf-8")).hexdigest()


def _build_llm_judge(options: dict[str, Any]) -> BoundScorer:
    model = options.get("model")
    if not model:
        raise ValueError("invalid_scorer_option:llm_judge needs a 'model'")
    template = str(options.get("prompt", DEFAULT_JUDGE_PROMPT))
    rubric = str(options.get("rubric", DEFAULT_RUBRIC))
    threshold = _threshold(options, 1.0)
    temperature = float(options.get("temperature", 0.0))
    litellm = _litellm()

    def score(expected: Any, predicted: Any, case_input: Any) -> tuple[float, dict[str, Any]]:
        prompt = template.format(
            input=json.dumps(case_input, ensure_ascii=False) if not isinstance(case_input, str)
            else case_input,
            expected=_text(expected),
            prediction=_text(predicted),
            rubric=rubric,
        )
        resp = litellm.completion(
            model=model, messages=[{"role": "user", "content": prompt}], temperature=temperature
        )
        choice = _get(resp, "choices")[0]
        raw = _text(_get(_get(choice, "message"), "content"))
        meta: dict[str, Any] = {"model": model, "prompt": prompt, "raw_response": raw}
        found = _JSON_OBJECT.search(raw)
        parsed: Any = None
        try:
            parsed = json.loads(found.group(0)) if found else None
            value = float(parsed["score"]) if isinstance(parsed, dict) else None
        except (ValueError, KeyError, TypeError):
            value = None
        if value is None or not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError(f"llm_judge: could not parse a score in [0, 1] from {raw[:200]!r}")
        if isinstance(parsed, dict) and parsed.get("reason") is not None:
            meta["reason"] = str(parsed["reason"])
        return _thresholded(value, threshold, meta)

    return score


BUILTIN_SCORERS: dict[str, BuiltinScorer] = {
    s.name: s
    for s in (
        BuiltinScorer("normalized_exact", _build_normalized_exact),
        BuiltinScorer("token_f1", _build_token_f1, options=("threshold",)),
        BuiltinScorer("fuzzy", _build_fuzzy, options=("threshold", "normalize")),
        BuiltinScorer("regex", _build_regex, options=("pattern", "mode", "ignore_case")),
        BuiltinScorer("numeric", _build_numeric, options=("abs_tol", "rel_tol", "extract")),
        BuiltinScorer("json_schema", _build_json_schema, options=("schema",)),
        BuiltinScorer("embedding", _build_embedding, network=True,
                      options=("model", "threshold")),
        BuiltinScorer("llm_judge", _build_llm_judge, network=True,
                      options=("model", "prompt", "rubric", "threshold", "temperature")),
    )
}


def describe_config(name: str, options: dict[str, Any]) -> dict[str, Any]:
    """Configuration recorded in the report for a built-in scorer (judge: model + prompt)."""
    record: dict[str, Any] = {"name": name, **options}
    if name == "llm_judge":
        template = str(options.get("prompt", DEFAULT_JUDGE_PROMPT))
        record.update(
            {
                "prompt": template,
                "prompt_sha256": judge_prompt_sha256(template),
                "rubric": str(options.get("rubric", DEFAULT_RUBRIC)),
                "temperature": float(options.get("temperature", 0.0)),
            }
        )
    return record
