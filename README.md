# Toolkit Eval Harness

[![PyPI](https://img.shields.io/pypi/v/toolkit-eval-harness.svg)](https://pypi.org/project/toolkit-eval-harness/)
[![Python versions](https://img.shields.io/pypi/pyversions/toolkit-eval-harness.svg)](https://pypi.org/project/toolkit-eval-harness/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

**An eval regression gate with signed evidence.** It decides, with a confidence interval,
whether a candidate model, prompt or pipeline is worse than the baseline on the same test
suite, and writes the decision as a standard, signable attestation (an in-toto Statement).

It works **with** the eval tools you already use: score predictions with its own
dependency-free scorers, or import results from promptfoo, Inspect AI or DeepEval, then gate
on them in CI with the CLI or the GitHub Action.

- **Statistically sound gate:** per-case flips, per-tag breakdown, and a seeded paired
  bootstrap confidence interval; the gate fails when the upper bound of the regression exceeds
  your budget, not just when the mean drops.
- **Same-suite binding:** reports carry a content digest of the suite, and `compare` refuses
  to compare results from different test sets.
- **Evidence:** canonical-JSON report envelopes (in-toto Statement v1) that standard tools can
  sign and verify; Ed25519-signed, manifest-checked suite packs.
- **Fail closed:** missing predictions, errored scorers and dropped cases fail.

The core has no runtime dependencies. Model-calling scorers (embedding similarity, LLM judge)
are optional extras and are off unless a run opts in.

## Status

Version 1.0.0, published on PyPI as `toolkit-eval-harness` (see [Install](#install)).

| Capability | Status | Notes |
|---|---|---|
| Exact-match scoring | Working | Python equality between `expected` and `prediction`. |
| JSON scoring (required keys + value checks) | Working | Checks required keys and compares values wherever `expected` is an object. |
| Plugin scorers (entry points or `register_scorer`) | Working | Must be listed in `scoring.scorers` to run. |
| Fail-closed case aggregation | Working | A case passes only if every required scorer passes; missing predictions fail. |
| `run` exit code gating | Working | Exits 1 when any case fails. |
| Suite packs (zip + SHA-256 manifest) | Working | Detects corruption and unlisted files; the manifest alone does not stop deliberate tampering. |
| Ed25519 pack signing, verified by `run` | Working | Needs the `signing` extra (`cryptography`). |
| Baseline comparison (`compare`) | Working | Same-suite check, per-case flips, per-tag breakdown, seeded paired-bootstrap CI; gates on the CI upper bound. See [Comparing reports](#comparing-reports). |
| Import promptfoo, Inspect AI and DeepEval results | Working | `toolkit-eval import`; see [Gating results from other tools](#gating-results-from-other-tools). |
| Report envelope (in-toto Statement v1, canonical JSON) | Working | Default for `run --out` and `compare --out`; see [Reports](#reports). |
| GitHub Action (`action.yml`) | Working | Runs `compare`, writes the job summary, optional PR comment. See [GitHub Action](#github-action). |
| JSON / table / CSV / Markdown output | Working | `--format`. |
| `MetricsCollector`, `check_health` | Partial | Library exports only; the CLI does not use them. |
| Built-in scorers: normalized exact, token F1, fuzzy, regex, numeric tolerance, JSON Schema | Working | See [Built-in scorers](#built-in-scorers). JSON Schema needs the `jsonschema` extra. |
| Embedding similarity and LLM judge (LiteLLM) | Working, opt-in | Off by default; need the `judge` extra and `--allow-network-scorers`. Tested with a stubbed LiteLLM, not against a live model. |
| Running models / generating predictions | Not planned | Out of scope by design. |
| Parallel evaluation | Planned | Cases are scored sequentially. |

## Install

Requires Python 3.10+.

```bash
pip install toolkit-eval-harness                 # core, no runtime dependencies
pip install "toolkit-eval-harness[signing]"      # adds pack signing (cryptography)
pip install "toolkit-eval-harness[inspect]"      # reads Zstandard-compressed Inspect .eval logs (zstandard)
pip install "toolkit-eval-harness[jsonschema]"   # adds the json_schema scorer (jsonschema)
pip install "toolkit-eval-harness[judge]"        # adds the embedding and LLM-judge scorers (LiteLLM)
toolkit-eval --help
```

To work on the code, see [Development](#development).

## 5-minute example

`examples/gsm8k-20/` holds the first 20 problems of the public
[GSM8K](https://github.com/openai/grade-school-math) test split (MIT license, see
`examples/gsm8k-20/LICENSE-GSM8K`) as a suite scored with the `numeric` scorer, plus two
prediction files. The predictions are **illustrative, not model outputs**: a script
(`make_predictions.py`) wrote a "baseline" that answers 17 of 20 correctly and a "candidate"
that answers 16, fixing one baseline mistake and making two new ones.

Run it from the root of a clone of this repository, which holds the example files:

```bash
git clone https://github.com/AKIVA-AI/toolkit-eval-harness.git
cd toolkit-eval-harness

# 1. Score both prediction files (exit 1 = some cases failed; the report is still written)
toolkit-eval run --suite examples/gsm8k-20 \
  --predictions examples/gsm8k-20/preds-baseline.jsonl --out baseline.json
toolkit-eval run --suite examples/gsm8k-20 \
  --predictions examples/gsm8k-20/preds-candidate.jsonl --out candidate.json

# 2. Gate the candidate against the baseline
toolkit-eval --format markdown compare --baseline baseline.json --candidate candidate.json \
  --out compare.json
```

The gate fails (exit 1):

| Metric | Value |
|---|---|
| Suite check | match |
| Paired cases | 20 |
| Baseline score / candidate score | 0.85 / 0.80 |
| Mean delta, 95% CI | -0.05, [-0.20, 0.10] |
| Regression: point / upper bound / budget | 5.88% / 23.53% / 2.00% |
| New failures / fixes | 2 (`gsm8k-test-0006`, `gsm8k-test-0013`) / 1 |

plus a per-tag table (`steps:2`, `steps:3`, `steps:4+`). With 20 cases the interval is wide:
the data cannot rule out a 23% regression, so even a 10% budget fails, whereas the pre-1.0
mean-only check (`--method mean`) would pass at 10%. `tests/test_example_gsm8k.py` checks these
numbers.

3. (Optional) sign the comparison as evidence with
[toolkit-ml-provenance](https://github.com/AKIVA-AI/toolkit-ml-provenance):

```bash
pip install "toolkit-ml-provenance[signing]"
toolkit-mlsbom keygen --private-key signing.pem --public-key signing.pub
toolkit-mlsbom sign-file compare.json --key signing.pem   # -> compare.json.sig.json
```

Already using promptfoo, Inspect AI or DeepEval? Replace step 1 with
`toolkit-eval import promptfoo results.json --out candidate.json` (or `inspect` / `deepeval`),
see [Gating results from other tools](#gating-results-from-other-tools). In CI, use the
[GitHub Action](#github-action).

### Signed suite packs

Needs the `signing` extra (`pip install "toolkit-eval-harness[signing]"`).

```bash
toolkit-eval pack create --suite-dir examples/suite --out packs/capitals.zip
toolkit-eval keygen --private-key signing.key --public-key signing.pub
toolkit-eval pack sign --suite packs/capitals.zip --private-key signing.key \
  --out packs/capitals.zip.sig.json
toolkit-eval run --suite packs/capitals.zip --public-key signing.pub \
  --predictions examples/preds.jsonl --out report.json
```

## File formats

A suite is a directory (or a pack zip) with two files.

`suite.json`:

```json
{
  "schema_version": 1,
  "name": "my-suite",
  "description": "optional",
  "created_at": "2026-01-01",
  "scoring": {
    "json_schema": {"required_keys": ["answer"], "optional_keys": [], "allow_extra_keys": true},
    "scorers": ["exact"]
  }
}
```

`scoring` is optional; see [Scoring semantics](#scoring-semantics).

`cases.jsonl`, one JSON object per line. `id` is required and must be unique; `input` is
stored but never read by the harness:

```json
{"id": "c1", "input": {"question": "Capital of France?"}, "expected": "Paris", "tags": ["geo"]}
```

Predictions JSONL, one object per line. `id` is required and must be unique:

```json
{"id": "c1", "prediction": "Paris"}
```

## Built-in scorers

List scorers in `scoring.scorers` by name, or as an object with options. `label` (default:
the name) names the result, so the same scorer can run twice with different options.

```json
"scoring": {
  "scorers": [
    "normalized_exact",
    {"name": "numeric", "extract": "last", "abs_tol": 0.01},
    {"name": "regex", "label": "cites_source", "pattern": "\\[\\d+\\]"},
    {"name": "json_schema", "schema": {"type": "object", "required": ["answer"]}}
  ]
}
```

| Name | Passes when | Options |
|---|---|---|
| `exact` | `prediction == expected` | none |
| `json` | required keys present and values equal (see below) | set via `scoring.json_schema` |
| `normalized_exact` | SQuAD-normalized strings are equal (lower-case, no punctuation or articles, single spaces); `expected` may be a list of accepted answers | none |
| `token_f1` | SQuAD token F1 >= `threshold` | `threshold` (1.0) |
| `fuzzy` | Levenshtein similarity `1 - distance / max(len)` >= `threshold` | `threshold` (0.9), `normalize`: `basic` (lower-case, squash spaces), `squad` or `none` |
| `regex` | `pattern` (or the case's `expected`) matches | `pattern`, `mode`: `search` or `fullmatch`, `ignore_case` |
| `numeric` | `math.isclose(prediction, expected, rel_tol, abs_tol)` | `abs_tol` (0), `rel_tol` (1e-9), `extract`: `full`, `first` or `last` number in the text |
| `json_schema` | prediction (object, or string holding JSON) validates against `schema` | `schema`; needs `pip install "toolkit-eval-harness[jsonschema]"` |
| `embedding` | cosine similarity of LiteLLM embeddings >= `threshold` | `model`, `threshold` (0.8) |
| `llm_judge` | the judge's score (0-1, parsed from its JSON reply) >= `threshold` | `model`, `rubric`, `prompt`, `threshold` (1.0), `temperature` (0) |

- Thresholded scorers return 1.0 at or above the threshold and the raw metric below it, so a
  near miss still counts as partial credit in `compare`.
- The SQuAD normalization, token F1 and Levenshtein results are checked in the tests against
  the official SQuAD v1.1 evaluation script and `rapidfuzz`.
- Unknown options, invalid thresholds and invalid regexes or schemas are input errors (exit 2).
  A scorer that raises on one case fails that case.
- **Network scorers are off by default.** `embedding` and `llm_judge` call a model through
  [LiteLLM](https://github.com/BerriAI/litellm) (`pip install "toolkit-eval-harness[judge]"`,
  provider keys in the usual LiteLLM environment variables). A suite that lists them is refused unless you pass
  `run --allow-network-scorers`. The report records the judge's model, prompt template and its
  SHA-256, rubric and temperature (`details.scorer_config`), and for every case the rendered
  prompt, the raw reply and the parsed reason. Judge results are only as reliable as the judge
  model; they are not deterministic across model versions.

## Scoring semantics

- **Required scorers.** `json` is required when `scoring.json_schema` is set. Every entry in
  `scoring.scorers` is also required: `exact`, `json` and the
  [built-in scorers](#built-in-scorers) are provided, and any other name must be a registered
  plugin scorer. With neither setting, the only required scorer is `exact`.
- **A case passes only if every required scorer returns 1.0.** Its score is the lowest
  required-scorer score, so a lenient scorer cannot mask a failure from a strict one.
- **JSON scorer.** The prediction (an object, or a string holding a JSON object) is checked
  once for each required key and once for each key of an `expected` object. A key passes if it
  is present and, when `expected` has that key, its value is equal. With
  `allow_extra_keys: false`, "no extra keys" is one more check. The score is the fraction of
  checks passed.
- **Missing predictions fail.** A case whose id is absent from the predictions file, or whose
  line has no `prediction` field, scores 0.0 and is flagged `missing_prediction`. This holds
  even when `expected` is null. An explicit `"prediction": null` is scored normally.
- **Input errors stop the run** (exit 2): an unknown scorer name, a prediction line without an
  `id`, a duplicate prediction id, or a duplicate case id. Prediction ids that match no case
  are counted in `summary.unknown_predictions` and otherwise ignored.
- **Plugin scorers.** A plugin that raises, or returns a score outside [0, 1], fails that case
  (score 0.0, `error: true`). The run continues with the other cases.

The report `summary` contains `cases`, `score` (mean case score), `passed`, `failed`,
`missing_predictions`, `unknown_predictions` and `scorers`. The CLI adds `pass_count`,
`fail_count`, `execution_time_seconds` and a `metadata` block.

## Gating results from other tools

The harness works **with** promptfoo, Inspect AI and DeepEval: keep producing results with
those tools, then use `toolkit-eval import` to turn them into a normalized report that
`compare` can gate on (and that you can sign).

```bash
toolkit-eval import promptfoo results.json --out candidate.json      # promptfoo eval -o results.json
toolkit-eval import inspect logs/2026-...eval --out candidate.json    # Inspect .eval or .json log
toolkit-eval import deepeval test_run.json --out candidate.json      # DEEPEVAL_RESULTS_FOLDER output
toolkit-eval compare --baseline baseline.json --candidate candidate.json
```

| Source | Tested with | Case id | Score | Passed | Suite digest covers |
|---|---|---|---|---|---|
| promptfoo `results.json` | promptfoo 0.123.1 (results version 3) | test description (unique) or `test-<idx>`; `@p<n>` / `@<provider>` added when several prompts / providers | promptfoo `score` | promptfoo `success` | vars + assertions |
| Inspect AI log (`.eval`, `.json`) | inspect_ai 0.3.270 | sample id (epochs reduced by mean) | lowest scorer value, mapped like Inspect's `value_to_float` (`C`=1, `P`=0.5, `I`/`N`=0) | every scorer value >= 1 | input + target |
| DeepEval test-run JSON | deepeval 4.2.6 | test case `name` | lowest metric score | DeepEval `success` | input + expected output + context |

- Filters: `--provider` (promptfoo), `--scorer` (Inspect), `--metric` (DeepEval).
- Fail closed: rows the tool marks as errors, metrics with an error or no score, and Inspect
  samples listed in the dataset but missing from the log fail with score 0.
- The suite digest covers each case's inputs, not its outputs, so two runs of the same tests
  (for example with a different prompt or model) share a digest and `compare` pairs them.
- Tags: promptfoo `provider:<id>` plus `key:value` from test metadata; Inspect `key:value`
  from sample metadata; DeepEval test-case `tags`.
- `import` exits 1 when any imported case failed (the report is still written), like `run`.
  The envelope kind is `eval.import`.
- Recent Inspect `.eval` logs are Zstandard-compressed. Python 3.14's `zipfile` reads them;
  on older Pythons install the `inspect` extra
  (`pip install "toolkit-eval-harness[inspect]"`, adds `zstandard`) or convert with `inspect log convert --to json`.

The formats are pinned by fixtures generated with the real tools; see
[tests/fixtures/importers/README.md](tests/fixtures/importers/README.md).

## Comparing reports

`toolkit-eval compare --baseline base.json --candidate cand.json` decides whether a candidate
report is acceptable against a baseline produced from the **same suite**.

1. **Same suite.** Both reports carry the suite content digest (`suite.sha256`). If they
   differ, `compare` refuses (exit 4, verdict `error`). `--allow-suite-mismatch` compares
   anyway, pairing only the case ids both reports share. Reports without a digest (pre-1.0)
   are compared with `suite_check: "unverified"`.
2. **Pairing.** Cases are paired by id. A baseline case missing from the candidate counts as a
   failure with score 0, so dropping a case cannot hide a regression.
3. **Flips.** `new_failures` lists cases that passed in the baseline and fail now; `fixes`
   lists the reverse. `--max-new-failures N` also fails the gate when more than N cases flip
   from pass to fail.
4. **Per-tag breakdown.** `per_tag` gives, for each tag, the case count, both mean scores,
   the delta and the flip counts.
5. **Confidence interval.** A paired percentile bootstrap resamples the per-case deltas
   (`candidate - baseline`) `--iterations` times (default 10000) with a seeded RNG
   (`--seed`, default 0) and reports the `--confidence` interval (default 0.95) for the mean
   delta as `ci_low` / `ci_high`. The same inputs and seed always give the same interval. The
   implementation is checked against `scipy.stats.bootstrap(paired=True,
   method="percentile")` in the test suite.
6. **Gate.** `regression_pct_upper = -ci_low / baseline_mean * 100` is the upper bound of the
   relative regression (the baseline mean over the paired cases is treated as fixed). The gate
   fails (exit 1) when it exceeds `--max-score-regression-pct` (default 2). So a change passes
   only when the data support "any regression is within budget", not just when the mean moved
   little: two cases broken and two fixed leave the mean unchanged but still fail a tight gate
   on a small suite. Use a larger suite, a looser budget or `--method mean` (the pre-1.0
   aggregate-mean check) if that is too strict for you.

Reports with no per-case scores fall back to the aggregate mean. Output keys: `passed`,
`reason` (`ok`, `score_regression`, `new_failures`, `suite_mismatch`, `no_baseline_score`,
`no_baseline_score_and_candidate_zero`), `method`, `suite_check`, `paired_cases`,
`baseline_score`, `candidate_score`, `mean_delta`, `ci_low`, `ci_high`, `confidence`,
`iterations`, `seed`, `score_regression_pct` (point estimate), `regression_pct_upper`,
`max_score_regression_pct`, `new_failures`, `fixes`, `new_failure_count`, `fix_count`,
`max_new_failures`, `per_tag`, `only_in_baseline`, `only_in_candidate`.

## GitHub Action

`action.yml` is a composite action that installs the harness from the action's own checkout,
runs `compare`, appends a Markdown summary to the job summary, optionally posts it as a PR
comment, and fails the step when the gate fails.

```yaml
permissions:
  contents: read
  pull-requests: write        # only needed for comment-on-pr
steps:
  - uses: actions/checkout@v4
  # ... produce candidate.json with `toolkit-eval run --out` or `toolkit-eval import`,
  # and fetch baseline.json (for example from your main branch's artifacts)
  - uses: AKIVA-AI/toolkit-eval-harness@v1.0.0
    id: gate
    with:
      baseline: baseline.json
      candidate: candidate.json
      max-score-regression-pct: "2"
      max-new-failures: "0"
      comment-on-pr: "true"
      github-token: ${{ secrets.GITHUB_TOKEN }}
  - uses: actions/upload-artifact@v4
    if: always()
    with:
      name: eval-compare
      path: eval-compare.json
```

Inputs: `baseline`, `candidate` (required); `max-score-regression-pct` (2), `confidence`
(0.95), `iterations` (10000), `seed` (0), `max-new-failures` (empty = not gated), `method`
(`bootstrap`), `allow-suite-mismatch` (`false`), `out` (`eval-compare.json`),
`python-version` (3.12), `install` (pip spec; default: the action checkout), `comment-on-pr`
(`false`), `github-token`, `fail-on-regression` (`true`). Outputs: `verdict`
(`pass`/`fail`/`error`), `exit-code`, `report`, `summary`. The PR comment edits the token's
last comment on the PR when there is one, so reruns do not pile up comments.
`.github/workflows/action-selftest.yml` exercises the action on every push.

`toolkit-eval --format markdown` produces the same summary locally.

## Pack integrity

- `pack create` writes `suite.json`, `cases.jsonl`, `pack.json` and a `manifest.json` with the
  SHA-256 of each suite file.
- `pack verify` and every pack load check each file against the manifest, and reject files the
  manifest does not list. Because the manifest is inside the same zip, this catches corruption
  and careless edits, **not deliberate tampering**.
- For tamper evidence, sign the pack (`pack sign`). `run` checks the signature before scoring
  when you pass `--signature`, or when a `<pack>.sig.json` file sits next to the pack. In both
  cases `--public-key` is required; `run` refuses to start without it, or if the signature does
  not match.
- Packs are read into memory. Nothing is extracted to disk during `run` or `pack inspect`.

## CLI commands

| Command | Purpose |
|---|---|
| `run` | Score predictions against a suite (directory or pack). |
| `compare` | Compare a candidate report with a baseline report. |
| `import` | Normalize promptfoo, Inspect AI or DeepEval results into a report. |
| `pack create` | Build a pack zip from a suite directory. |
| `pack verify` | Check a pack against its manifest. |
| `pack inspect` | Print suite metadata (directory or pack). |
| `pack sign` | Write a detached Ed25519 signature for a pack. |
| `pack verify-signature` | Check a pack signature. |
| `keygen` | Generate an Ed25519 key pair. |
| `validate-report` | Check a report: the envelope structure, or the pre-1.0 report shape. |
| `check-deps` | Report Python version, the optional `cryptography` dependency and registered plugin scorers. |

Global options: `--format json|table|csv|markdown`, `--output FILE`, `-v/--verbose`, `-q/--quiet`,
`--log-format text|json`, `--log-file FILE`. Logs go to stderr and data to stdout.

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Success. For `run`, every case passed; for `compare`, the gate passed. Envelope verdict `pass`. |
| `1` | Gate failed. `run`: at least one case failed or had no prediction, or the suite has no cases. `compare`: regression over budget. The report is still written. Envelope verdict `fail`. |
| `2` | Usage or input error: bad arguments, missing or malformed files. Verdict `error`. |
| `3` | Unexpected internal error. Verdict `error`. |
| `4` | Integrity failure: pack manifest or signature check failed, `compare` was given reports from different suites, or `validate-report` found problems. Verdict `error`. |

Before 1.0, `compare` exited `4` when the regression was over budget; it now exits `1`.

## Reports

`run --out FILE` and `compare --out FILE` write a **report envelope**: an
[in-toto Statement v1](https://github.com/in-toto/attestation/blob/main/spec/v1/statement.md)
in canonical JSON (UTF-8, sorted keys, no insignificant whitespace, trailing newline), so the
file's SHA-256 is stable and the report can be signed and verified with standard tooling. The
format is shared by the toolkit family: see [docs/report-envelope.md](docs/report-envelope.md)
and the JSON Schema [schemas/report-envelope.v1.json](schemas/report-envelope.v1.json).

- `subject`: the suite, identified by its **content digest** (SHA-256 of the canonical JSON of
  the suite metadata and cases; a directory and a pack built from it have the same digest).
  For a pack that fails verification it is the pack file.
- `predicate.kind`: `eval.run` or `eval.compare`.
- `predicate.verdict` / `exit_code`: `pass`/0, `fail`/1, or `error` with the exit codes above.
- `predicate.inputs`: the suite (pack file digest, or suite digest for a directory) and the
  predictions file for `run`; the two report files for `compare`.
- `predicate.summary` for `eval.run`: `cases`, `passed`, `failed`, `pass_rate`, `score`
  (mean case score), `missing_predictions`, `unknown_predictions`, `scorers`.
- `predicate.details` for `eval.run`: `suite` (metadata and `sha256`), `cases` (per-case
  results) and `environment`.
- `predicate.summary` for `eval.compare`: `reason`, `method`, `suite_check`,
  `paired_cases`, `baseline_score`, `candidate_score`, `mean_delta`, `ci_low`, `ci_high`,
  `confidence`, `score_regression_pct`, `regression_pct_upper`, `max_score_regression_pct`,
  `new_failure_count`, `fix_count`, `max_new_failures`. `details` holds the rest (flipped case
  ids, `per_tag`, bootstrap `iterations` and `seed`, suite digests).

Set `SOURCE_DATE_EPOCH` to fix `created_at`; the same inputs then give a byte-identical report.
`compare` and `validate-report` read both envelopes and pre-1.0 reports. `run --legacy-json`
writes the pre-1.0 report format instead; it is deprecated and will be removed in 1.1.
Stdout output (`--format json|table|csv`) is unchanged.

**Signing a report** (optional, with
[toolkit-ml-provenance](https://github.com/AKIVA-AI/toolkit-ml-provenance)):

```bash
pip install "toolkit-ml-provenance[signing]"
toolkit-mlsbom keygen --private-key signing.pem --public-key signing.pub
toolkit-mlsbom sign-file report.json --key signing.pem   # or --sigstore, with its [sigstore] extra
toolkit-mlsbom verify-file report.json --public-key signing.pub
```

## Plugin scorers

See [CONTRIBUTING.md](CONTRIBUTING.md#writing-custom-scorers-plugin-system). A registered
scorer runs only when its name is listed in the suite's `scoring.scorers`.

## Library use

```python
from pathlib import Path
from toolkit_eval_harness import load_suite_from_path, run_suite

suite = load_suite_from_path(Path("examples/suite"))
report = run_suite(suite=suite, predictions_path=Path("examples/preds.jsonl"))
print(report.summary)
```

## Development

Install from source in editable mode, with the test, lint and type-check tools:

```bash
git clone https://github.com/AKIVA-AI/toolkit-eval-harness.git
cd toolkit-eval-harness
pip install -e ".[dev]"
pytest -q
ruff check .
pyright src/
```

## Contributing and security

Contributions are welcome: see [CONTRIBUTING.md](CONTRIBUTING.md) and the
[Code of Conduct](CODE_OF_CONDUCT.md). Please report security problems
privately, as described in [SECURITY.md](SECURITY.md).

## Releasing

Releases are cut by pushing a `vX.Y.Z` tag. CI runs the tests, builds the
sdist and wheel, checks them, attaches them to a GitHub Release and publishes
them to PyPI with Trusted Publishing. [RELEASING.md](RELEASING.md) describes
the process and how to verify a release.

## License

Apache License 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).

Releases before the relicensing remain available under the MIT license.
