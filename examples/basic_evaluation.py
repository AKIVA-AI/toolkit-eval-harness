"""
Example: Basic Evaluation Workflow

This example demonstrates the complete evaluation workflow:
1. Create a test suite directory with suite.json and cases.jsonl
2. Package it into a suite pack
3. Run evaluation against predictions
4. Compare against a baseline report
"""

import json
from pathlib import Path

from toolkit_eval_harness.pack import create_pack, load_suite_from_path
from toolkit_eval_harness.runner import run_suite
from toolkit_eval_harness.compare import CompareBudget, compare_reports
from toolkit_eval_harness.report import EvalReport


def main():
    """Main example workflow."""
    print("=" * 60)
    print("Toolkit Eval Harness - Basic Evaluation Example")
    print("=" * 60)

    # Step 1: Create test suite directory
    print("\nStep 1: Creating test suite directory...")
    suite_dir = Path("temp_suite")
    suite_dir.mkdir(exist_ok=True)

    suite_meta = {
        "schema_version": 1,
        "name": "sentiment-analysis-v1",
        "description": "Sentiment analysis evaluation suite",
        "created_at": "2026-01-01T00:00:00Z",
        "scoring": {},
    }

    cases = [
        {
            "id": "test_001",
            "input": {"text": "I love this product!"},
            "expected": {"sentiment": "positive", "confidence": 0.95},
            "tags": ["positive", "high-confidence"],
        },
        {
            "id": "test_002",
            "input": {"text": "This is terrible."},
            "expected": {"sentiment": "negative", "confidence": 0.90},
            "tags": ["negative", "high-confidence"],
        },
        {
            "id": "test_003",
            "input": {"text": "It's okay, nothing special."},
            "expected": {"sentiment": "neutral", "confidence": 0.70},
            "tags": ["neutral", "medium-confidence"],
        },
    ]

    with open(suite_dir / "suite.json", "w") as f:
        json.dump(suite_meta, f, indent=2)

    with open(suite_dir / "cases.jsonl", "w") as f:
        for case in cases:
            f.write(json.dumps(case) + "\n")

    print(f"  Created suite with {len(cases)} test cases")

    # Step 2: Create suite pack
    print("\nStep 2: Creating suite pack...")
    pack_path = Path("sentiment_suite.zip")
    create_pack(suite_dir=suite_dir, out_zip=pack_path)
    print(f"  Suite pack created: {pack_path}")

    # Step 3: Create predictions file
    print("\nStep 3: Writing model predictions...")
    predictions = [
        {"id": "test_001", "prediction": {"sentiment": "positive", "confidence": 0.95}},
        {"id": "test_002", "prediction": {"sentiment": "negative", "confidence": 0.88}},
        {"id": "test_003", "prediction": {"sentiment": "neutral", "confidence": 0.65}},
    ]

    predictions_file = Path("predictions.jsonl")
    with open(predictions_file, "w") as f:
        for pred in predictions:
            f.write(json.dumps(pred) + "\n")

    print(f"  Generated {len(predictions)} predictions")

    # Step 4: Run evaluation
    print("\nStep 4: Running evaluation...")
    suite = load_suite_from_path(pack_path)
    report = run_suite(suite=suite, predictions_path=predictions_file)

    print("  Evaluation complete!")
    print(f"  Cases: {report.summary['cases']}")
    print(f"  Score: {report.summary['score']:.2%}")

    # Save results
    results_file = Path("evaluation_results.json")
    with open(results_file, "w") as f:
        json.dump(report.to_dict(), f, indent=2)

    # Step 5: Compare against a baseline
    print("\nStep 5: Comparing against baseline...")

    # Simulate a baseline report (perfect scores)
    baseline = EvalReport(
        suite=report.suite,
        summary={"cases": 3, "score": 1.0},
        cases=[],
    )

    budget = CompareBudget(max_score_regression_pct=5.0)
    result = compare_reports(baseline=baseline, candidate=report, budget=budget)

    if result["passed"]:
        print("  No regression detected")
    else:
        print(f"  Regression detected: {result['reason']}")
        print(f"  Score regression: {result['score_regression_pct']:.2f}%")

    # Cleanup
    print("\nCleaning up...")
    (suite_dir / "suite.json").unlink()
    (suite_dir / "cases.jsonl").unlink()
    suite_dir.rmdir()
    pack_path.unlink()
    predictions_file.unlink()
    results_file.unlink()

    # Clean up temporary unpack directory if it exists
    tmp_dir = pack_path.parent / f".toolkit_eval_unpack_{pack_path.stem}"
    if tmp_dir.exists():
        for p in tmp_dir.rglob("*"):
            if p.is_file():
                p.unlink()
        for p in sorted([x for x in tmp_dir.rglob("*") if x.is_dir()], reverse=True):
            p.rmdir()
        tmp_dir.rmdir()

    print("\n" + "=" * 60)
    print("Example Complete!")
    print("=" * 60)
    print("\nKey Takeaways:")
    print("1. Create versioned test suites (suite.json + cases.jsonl)")
    print("2. Package suites into distributable packs")
    print("3. Run deterministic evaluations")
    print("4. Compare against baselines to detect regressions")
    print("5. Integrate into CI/CD pipelines")


if __name__ == "__main__":
    main()
