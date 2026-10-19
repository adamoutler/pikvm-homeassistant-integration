# E2E Test Infra: PiKVM Home Assistant Integration

## Test Philosophy
- Opaque-box, requirement-driven testing derived from Home Assistant Integration Quality Scale specifications and user requirements in `ORIGINAL_REQUEST.md`.
- Methodology: Category-Partition + Boundary Value Analysis (BVA) + Pairwise Combinatorial Testing + Real-World Workload Testing across all 54 HA Quality Scale rules.
- Public, reproducible verification via pytest in local environment and GitHub Actions CI.

## Feature Inventory
| # | Feature | Source (requirement) | Tier 1 | Tier 2 | Tier 3 |
|---|---------|---------------------|:------:|:------:|:------:|
| 1 | Device Setup & Zeroconf Discovery | ORIGINAL_REQUEST §R1 | 5 | 5 | ✓ |
| 2 | Coordinator Polling & Translated Exceptions | ORIGINAL_REQUEST §R1 | 5 | 5 | ✓ |
| 3 | Sensor & Long-Term Statistics Platform | ORIGINAL_REQUEST §R1 | 5 | 5 | ✓ |
| 4 | Binary Sensor & Dynamic State Icons | ORIGINAL_REQUEST §R1 | 5 | 5 | ✓ |
| 5 | Diagnostics & Redaction | ORIGINAL_REQUEST §R1 | 5 | 5 | ✓ |
| 6 | Options Flow & Reconfigure/Reauth | ORIGINAL_REQUEST §R1 | 5 | 5 | ✓ |
| 7 | Self-Healing Repairs (Undervoltage/Throttling) | ORIGINAL_REQUEST §R1 | 5 | 5 | ✓ |
| 8 | Stale Device & Config Entry Removal | ORIGINAL_REQUEST §R1 | 5 | 5 | ✓ |
| 9 | Strict Static Typing (PEP 561 / mypy --strict) | ORIGINAL_REQUEST §R2 | 5 | 5 | ✓ |
| 10 | Quality Scale Tracking & Translations Synchronization | ORIGINAL_REQUEST §R2 | 5 | 5 | ✓ |

## Test Architecture
- Test runner: `.venv/bin/pytest --cov=custom_components.pikvm --cov-report=term-missing --cov-fail-under=100`
- Linter & Type Checker: `.venv/bin/mypy --strict custom_components/pikvm` and `.venv/bin/ruff check custom_components/pikvm tests`
- Test directory: `tests/`
- Test fixtures: `tests/conftest.py` with mock PiKVM client, mock responses, and Home Assistant test fixtures.

## Real-World Application Scenarios (Tier 4)
| # | Scenario | Features Exercised | Complexity |
|---|----------|--------------------|------------|
| 1 | Fresh Zeroconf Discovery to Ingestion & Sensor Generation | F1, F3, F4, F9 | Medium |
| 2 | PiKVM Hardware Reboot & Transient Network Disconnect Recovery | F2, F7, F8 | High |
| 3 | 2FA TOTP Credential Rotation & Reauth Flow with Token Invalidation | F1, F2, F6 | High |
| 4 | PiKVM Hardware Throttling, Repairs Issue Generation & Self-Healing | F2, F4, F7 | High |
| 5 | IP Address Reallocation via mDNS Discovery Update & Unload Lifecycle | F1, F8, F10 | Medium |

## Coverage Thresholds
- Tier 1: ≥5 per feature (50 test cases)
- Tier 2: ≥5 per feature (50 boundary/corner test cases)
- Tier 3: Pairwise coverage of major feature interactions (10 test cases)
- Tier 4: ≥5 realistic application scenarios (5 test cases)
- Target: 100% statement and branch coverage on `custom_components/pikvm`.
