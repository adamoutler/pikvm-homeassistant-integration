# PiKVM Home Assistant Integration - Project Manifest

## Overview
Custom integration for Home Assistant providing monitoring and management of PiKVM devices.
Domain: `pikvm_ha`

## Architecture & Module Structure
- `custom_components/pikvm_ha/__init__.py`: Component lifecycle, setup, unload, entry update listeners.
- `custom_components/pikvm_ha/coordinator.py`: `PiKVMDataUpdateCoordinator` managing asynchronous polling via `pikvm-aio`.
- `custom_components/pikvm_ha/config_flow.py`: User configuration flow and zeroconf auto-discovery.
- `custom_components/pikvm_ha/options_flow.py`: Runtime configuration options (e.g. polling intervals, cert validation).
- `custom_components/pikvm_ha/cert_handler.py`: Certificate handling, SSL context and pinning.
- `custom_components/pikvm_ha/entity.py`: Base entity definitions.
- `custom_components/pikvm_ha/sensor.py` & `sensors/`: Concrete sensor platforms for PiKVM metrics.
- `custom_components/pikvm_ha/diagnostics.py`: Redacted diagnostic data dumping.
- `custom_components/pikvm_ha/utils.py`: Common helpers.

## Security & Operational Invariants
- **Hostile Wire / Zero Cleartext:** Sensitive credentials (passwords, base32 TOTP secrets) must never be logged or leaked into unredacted diagnostics.
- **Fail-Safe Polling:** Network timeouts, certificate errors, and authorization failures must be handled gracefully in `PiKVMDataUpdateCoordinator` without unhandled exceptions or crashing Home Assistant.
- **Zero-Tolerance Quality:** Strict type hints and safe casting across all platform entities.

## Testing & Quality Standard
- Minimum test coverage: **80%** enforced in CI (`pytest --cov=custom_components.pikvm_ha --cov-fail-under=80`).
- Public verification executed via GitHub Actions (`tests.yaml`, `hassfest.yaml`, `validate.yaml`).
