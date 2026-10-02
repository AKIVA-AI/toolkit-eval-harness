"""Offline DeepEval run for importer fixtures: a deterministic custom metric, no LLM calls."""
from deepeval import evaluate
from deepeval.metrics import BaseMetric
from deepeval.test_case import LLMTestCase


class ContainsExpected(BaseMetric):
    def __init__(self, threshold: float = 1.0):
        self.threshold = threshold

    def measure(self, test_case: LLMTestCase) -> float:
        self.score = 1.0 if test_case.expected_output in test_case.actual_output else 0.0
        self.success = self.score >= self.threshold
        self.reason = "contains expected" if self.success else "missing expected"
        return self.score

    async def a_measure(self, test_case: LLMTestCase) -> float:
        return self.measure(test_case)

    def is_successful(self) -> bool:
        return self.success

    @property
    def __name__(self):
        return "Contains Expected"


class LengthUnder(BaseMetric):
    def __init__(self, limit: int = 30, threshold: float = 0.5):
        self.limit = limit
        self.threshold = threshold

    def measure(self, test_case: LLMTestCase) -> float:
        self.score = min(1.0, self.limit / max(1, len(test_case.actual_output)))
        self.success = self.score >= self.threshold
        self.reason = f"length {len(test_case.actual_output)}"
        return self.score

    async def a_measure(self, test_case: LLMTestCase) -> float:
        return self.measure(test_case)

    def is_successful(self) -> bool:
        return self.success

    @property
    def __name__(self):
        return "Length Under"


cases = [
    LLMTestCase(name="france", input="Capital of France?", actual_output="Paris", expected_output="Paris", tags=["geo"]),
    LLMTestCase(name="japan", input="Capital of Japan?", actual_output="Kyoto", expected_output="Tokyo", tags=["geo"]),
    LLMTestCase(name="essay", input="Say hi", actual_output="hi " * 40, expected_output="hi", tags=["style"]),
]
evaluate(test_cases=cases, metrics=[ContainsExpected(), LengthUnder()])
