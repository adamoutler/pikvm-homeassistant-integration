# PiKVM Home Assistant Integration - Project Manifest

## Overview
Custom integration for Home Assistant providing monitoring and management of PiKVM devices (V2, V3, V4 Mini, V4 Plus, and DIY KVMD setups).
Domain: `pikvm`
Integration Type: Device / Local Polling
Quality Scale Target: Platinum

## Architecture & Module Structure
- `custom_components/pikvm/__init__.py`: Component lifecycle, setup, unload, remove, device registry reconciliation, title disambiguation, and runtime data assignment (`entry.runtime_data`).
- `custom_components/pikvm/coordinator.py`: `PiKVMDataUpdateCoordinator` managing async polling via `pikvm-aio`, translating auth/connection errors (`ConfigEntryAuthFailed`, `UpdateFailed`), and dispatching self-healing Repairs issues (`issue_registry`) for undervoltage and throttling.
- `custom_components/pikvm/config_flow.py`: User configuration, Zeroconf discovery (IPv4 filtered), Reauth flow (with TOTP clearing support), and Reconfigure flow (with serial mismatch guard).
- `custom_components/pikvm/options_flow.py`: Runtime configuration options (`scan_interval`: 5 to 300 seconds).
- `custom_components/pikvm/cert_handler.py`: Certificate acquisition and device verification using `pikvm-aio`.
- `custom_components/pikvm/entity.py`: Base entity class, `PiKVMEntityDescriptionMixin`, and shared stale entity cleanup linking entities to coordinator telemetry and DeviceInfo.
- `custom_components/pikvm/sensor.py`: Numeric sensor platform with Long-Term Statistics (LTS) support (CPU temp, CPU util, memory util, fan speed, MSD storage).
- `custom_components/pikvm/binary_sensor.py`: Binary sensor platform for state flags (throttling, MSD enabled/drive, extra services).
- `custom_components/pikvm/diagnostics.py`: Redacted diagnostic data dumping for config entries and device registry entries.
- `custom_components/pikvm/utils.py`: Helpers for URL normalization, schema generation, `PiKVMDeviceInfo` coercion, and safe nested data retrieval.
- `custom_components/pikvm/strings.json` & `translations/en.json`: UI and issue translations.
- `custom_components/pikvm/icons.json`: Decoupled MDI icon definitions for entities.

## Security & Operational Invariants
- **Hostile Wire / Zero Cleartext:** Sensitive credentials (passwords, base32 TOTP secrets, certificates, auth tokens) must never be logged or leaked into unredacted diagnostics.
- **Non-Compliant Hardware Certificates:** Stock PiKVM hardware generates self-signed certificates with generic CN (`localhost`) and missing CA BasicConstraints / IP SANs. We fetch and store the certificate to detect new clients and encrypt traffic rather than to verify the host via CA chain (`verify_ssl=False`, `check_hostname=False`), while injecting Home Assistant's shared `aiohttp.ClientSession` (`inject-websession`).
- **Ephemeral 2FA:** TOTP codes are generated ephemerally via `pyotp` during authentication handshakes and never persisted to disk or logged. Submitting an empty string or whitespace during reauth/reconfigure cleanly removes and clears the stored TOTP key.
- **Fail-Safe Polling:** Network timeouts, certificate errors, and authorization failures are handled gracefully without unhandled exceptions or crashing Home Assistant (`ConfigEntryAuthFailed` on auth failure, `UpdateFailed` on network/device error).
- **Long-Term Statistics (LTS):** Continuous telemetry sensors enforce `state_class = SensorStateClass.MEASUREMENT`, valid `SensorDeviceClass`, native units, and display precision.
- **Platform Separation:** Boolean entities reside in `binary_sensor.py`, while continuous numeric entities reside in `sensor.py`. `SensorEntity.unit_of_measurement` is `@final` in HA 2024.10+; never override it—use `SensorEntityDescription.native_unit_of_measurement` or `_attr_native_unit_of_measurement`.
- **Self-Healing Repairs:** Hardware undervoltage and throttling automatically create entries in the Home Assistant Repairs dashboard (`IssueSeverity.CRITICAL` / `IssueSeverity.WARNING`) and delete them once resolved.
- **Concurrency Control:** `PARALLEL_UPDATES = 0` is enforced across all platforms.
- **Zero-Tolerance Quality:** Strict type hints, safe casting, and 100% test coverage target.

## Testing & Quality Standard
- Test coverage: **100%** enforced in CI (`pytest --cov=custom_components.pikvm --cov-fail-under=100`).
- Public verification executed via GitHub Actions (`tests.yaml`, `hassfest.yaml`, `validate.yaml`).
