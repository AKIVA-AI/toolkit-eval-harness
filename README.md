# Toolkit Eval Harness

Enterprise-grade evaluation framework for AI/ML models with versioned test suites, deterministic scoring, and CI/CD integration for regression testing.

## Overview

The Toolkit Eval Harness is a lightweight, powerful evaluation tool designed for AI/ML engineers to version "golden" task suites, score predictions with deterministic metrics, and produce CI-friendly JSON reports with regression comparisons. It complements Neural Forge model lifecycle gates and provides a solid foundation for model evaluation in production environments.

## Key Features

### Test Suite Management
- **Versioned Test Suites**: Immutable, version-controlled evaluation datasets
- **Deterministic Scoring**: Consistent, reproducible evaluation metrics
- **Suite Packs**: Compressed, hash-verified test suite packages
- **Digital Signatures**: Optional cryptographic signing for integrity verification

### Comprehensive Evaluation
- **Multiple Scoring Methods**: Exact match, JSON schema validation, custom metrics
- **Flexible Test Cases**: Support for various input/output formats
- **Tagging System**: Organize tests by category, difficulty, or use case
- **Batch Processing**: Efficient evaluation of large test suites

### Enterprise Integration
- **CI/CD Friendly**: JSON reports with exit codes for pipeline integration
- **Regression Detection**: Automated comparison against baseline evaluations
- **Audit Trails**: Complete evaluation history and provenance tracking
- **Performance Metrics**: Latency, throughput, and resource usage tracking

### Security and Compliance
- **Package Signing**: Ed25519 cryptographic signatures for integrity
- **Hash Verification**: SHA-256 checksums for all packages
- **Access Control**: Role-based permissions for suite management
- **Audit Logging**: Complete evaluation audit trails

## Quick Start

### Installation

```bash
# Install from source
git clone https://github.com/AKIVA-AI/toolkit-eval-harness.git
cd toolkit-eval-harness
pip install -e ".[dev]"

# Install with signing support
pip install -e ".[signing]"

# Install in production
pip install toolkit-eval-harness
```

### Basic Usage

```bash
# 1. Create a test suite pack
toolkit-eval pack create --suite-dir examples/suite --out packs/suite.zip

# 2. Verify pack integrity
toolkit-eval pack verify --suite packs/suite.zip

# 3. Run evaluation
toolkit-eval run --suite packs/suite.zip --predictions examples/preds.jsonl --out report.json

# 4. Compare with baseline (CI gating)
toolkit-eval compare --baseline baseline.json --candidate report.json
```

## CLI Commands

- `pack create` - Create a suite pack from a directory
- `pack verify` - Verify pack integrity (hashes)
- `pack sign` - Sign suite packs (optional)
- `pack verify-signature` - Verify pack signatures
- `run` - Run evaluation against predictions
- `compare` - Compare candidate report to baseline (CI gating)
- `keygen` - Generate signing keys

## Exit Codes

- `0` - Success
- `1` - General error
- `4` - Regression detected (for compare command)

## License

MIT License - see LICENSE file for details.
