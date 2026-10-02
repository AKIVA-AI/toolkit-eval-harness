"""Offline Inspect AI task for importer fixtures (mockllm/model, no API keys)."""
from inspect_ai import Task, task
from inspect_ai.dataset import Sample
from inspect_ai.scorer import includes, match
from inspect_ai.solver import generate


def samples():
    return [
        Sample(id="fr", input="Capital of France?", target="Default output", metadata={"topic": "geo"}),
        Sample(id="jp", input="Capital of Japan?", target="Tokyo", metadata={"topic": "geo"}),
        Sample(id="math-1", input="2+2?", target="output from mockllm", metadata={"topic": "math"}),
    ]


@task
def capitals():
    return Task(dataset=samples(), solver=[generate()], scorer=[includes(), match(location="any")])
