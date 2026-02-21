"""
Example: Basic Evaluation Workflow

This example demonstrates the complete evaluation workflow:
1. Create a test suite
2. Package it into a suite pack
3. Run evaluation against predictions
4. Check for regressions
"""

import json
from pathlib import Path
from toolkit_eval_harness.suite import TestSuite, TestCase
from toolkit_eval_harness.pack import create_pack, load_suite_from_zip
from toolkit_eval_harness.eval import evaluate
from toolkit_eval_harness.regression import check_regression


def main():
    """Main example workflow"""
    print("=" * 60)
    print("ðŸ” Toolkit Eval Harness - Basic Evaluation Example")
    print("=" * 60)
    
    # Step 1: Create test suite
    print("\nðŸ“ Step 1: Creating test suite...")
    suite = TestSuite(
        name="sentiment-analysis-v1",
        version="1.0.0",
        description="Sentiment analysis evaluation suite"
    )
    
    # Add test cases
    test_cases = [
        TestCase(
            id="test_001",
            input={"text": "I love this product!"},
            expected_output={"sentiment": "positive", "confidence": 0.95},
            tags=["positive", "high-confidence"]
        ),
        TestCase(
            id="test_002",
            input={"text": "This is terrible."},
            expected_output={"sentiment": "negative", "confidence": 0.90},
            tags=["negative", "high-confidence"]
        ),
        TestCase(
            id="test_003",
            input={"text": "It's okay, nothing special."},
            expected_output={"sentiment": "neutral", "confidence": 0.70},
            tags=["neutral", "medium-confidence"]
        ),
    ]
    
    for tc in test_cases:
        suite.add_test_case(tc)
    
    print(f"âœ… Created suite with {len(test_cases)} test cases")
    
    # Step 2: Create suite pack
    print("\nðŸ“¦ Step 2: Creating suite pack...")
    suite_dir = Path("temp_suite")
    suite_dir.mkdir(exist_ok=True)
    
    suite_file = suite_dir / "suite.json"
    with open(suite_file, "w") as f:
        json.dump(suite.to_dict(), f, indent=2)
    
    pack_path = Path("sentiment_suite.zip")
    create_pack(suite_dir, pack_path)
    print(f"âœ… Suite pack created: {pack_path}")
    
    # Step 3: Simulate predictions
    print("\nðŸ¤– Step 3: Simulating model predictions...")
    predictions = [
        {"id": "test_001", "output": {"sentiment": "positive", "confidence": 0.95}},
        {"id": "test_002", "output": {"sentiment": "negative", "confidence": 0.88}},
        {"id": "test_003", "output": {"sentiment": "neutral", "confidence": 0.65}},
    ]
    
    predictions_file = Path("predictions.jsonl")
    with open(predictions_file, "w") as f:
        for pred in predictions:
            f.write(json.dumps(pred) + "\n")
    
    print(f"âœ… Generated {len(predictions)} predictions")
    
    # Step 4: Run evaluation
    print("\nâœ… Step 4: Running evaluation...")
    loaded_suite = load_suite_from_zip(pack_path)
    results = evaluate(loaded_suite, predictions)
    
    print(f"âœ… Evaluation complete!")
    print(f"   Total: {results['total']}")
    print(f"   Passed: {results['passed']}")
    print(f"   Failed: {results['failed']}")
    print(f"   Accuracy: {results['accuracy']:.2%}")
    
    # Save results
    results_file = Path("evaluation_results.json")
    with open(results_file, "w") as f:
        json.dump(results, f, indent=2)
    
    # Step 5: Check for regression
    print("\nðŸ” Step 5: Checking for regression...")
    
    # Simulate baseline results
    baseline_results = {
        "total": 3,
        "passed": 3,
        "failed": 0,
        "accuracy": 1.0
    }
    
    regression_result = check_regression(results, baseline_results)
    
    if regression_result["regression_detected"]:
        print(f"âš ï¸  Regression detected!")
        print(f"   Accuracy drop: {regression_result['accuracy_drop']:.2%}")
    else:
        print(f"âœ… No regression detected")
        print(f"   Performance maintained or improved")
    
    # Cleanup
    print("\nðŸ§¹ Cleaning up...")
    suite_file.unlink()
    suite_dir.rmdir()
    pack_path.unlink()
    predictions_file.unlink()
    results_file.unlink()
    
    print("\n" + "=" * 60)
    print("âœ… Example Complete!")
    print("=" * 60)
    print("\nKey Takeaways:")
    print("1. Create versioned test suites")
    print("2. Package suites into distributable packs")
    print("3. Run deterministic evaluations")
    print("4. Detect regressions automatically")
    print("5. Integrate into CI/CD pipelines")


if __name__ == "__main__":
    main()



