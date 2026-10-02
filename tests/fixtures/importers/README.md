# Importer fixtures

Every file here was produced by the tool itself, offline, in a disposable container, so the
importer tests pin the formats the tools actually write. Nothing was edited by hand.

## promptfoo 0.123.1 (`promptfoo/`)

Config files: `promptfooconfig.yaml` (baseline) and `candidate.yaml` (same tests, different
prompt). Both use promptfoo's built-in `echo` provider, which returns the rendered prompt, so
no API key or network model is involved.

```sh
docker run --rm -v "$PWD:/p" -w /p -e PROMPTFOO_DISABLE_TELEMETRY=1 node:22 \
  sh -c "npx -y promptfoo@0.123.1 eval -c promptfooconfig.yaml -o baseline.json --no-cache &&
         npx -y promptfoo@0.123.1 eval -c candidate.yaml -o candidate.json --no-cache"
```

## Inspect AI 0.3.270 (`inspect/`)

Task: `task.py` (three samples, scorers `includes()` and `match(location="any")`), run with
the built-in `mockllm/model`, which needs no API key.

```sh
docker run --rm -v "$PWD:/i" -w /i python:3.12-slim sh -c "pip install inspect-ai==0.3.270 &&
  inspect eval task.py --model mockllm/model --log-dir logs-eval &&
  inspect eval task.py --model mockllm/model --log-dir logs-json --log-format json &&
  inspect eval task.py --model mockllm/model --log-dir logs-epochs --epochs 2"
```

`capitals.eval`, `capitals.json` and `capitals-2-epochs.eval` are those three logs, renamed.
The `.eval` members are Zstandard-compressed.

## DeepEval 4.2.6 (`deepeval/`)

Script: `run_eval.py` (three test cases, two deterministic custom metrics, no LLM calls).

```sh
docker run --rm -v "$PWD:/d" -w /d -e DEEPEVAL_TELEMETRY_OPT_OUT=YES \
  -e DEEPEVAL_RESULTS_FOLDER=/d/out python:3.12-slim \
  sh -c "pip install deepeval==4.2.6 && python run_eval.py"
```

`test_run.json` is the file DeepEval saved in `out/`, renamed.
