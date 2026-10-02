# Security policy

## Supported versions

| Version | Supported |
| ------- | --------- |
| 1.0.x   | Yes       |
| < 1.0   | No        |

Security fixes are released as patch versions of the latest minor release.

## Reporting a vulnerability

Please do not report security problems in a public issue, pull request or
discussion. Report them privately through GitHub: open this repository's
**Security** tab and choose **Report a vulnerability**
(<https://github.com/AKIVA-AI/toolkit-eval-harness/security/advisories/new>). Include:

- what the problem is and its impact;
- steps or input files to reproduce it;
- the affected version or commit.

We aim to acknowledge a report within 7 days and ask for up to 90 days to
release a fix before public disclosure. We credit reporters who want to be
credited.

## Guidance

- Treat suites, predictions, and model outputs as untrusted input.
- Run in a sandboxed CI environment when evaluating untrusted content.
