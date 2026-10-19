# Project: PiKVM Home Assistant Integration - Gold & Platinum Quality Scale Compliance

## Architecture
- Custom component domain: `pikvm` (with migration from legacy `pikvm_ha`)
- Architecture pattern: Device Integration / Local Polling via async `pikvm-aio`
- Data flow:
  1. `config_flow.py`: Discovers PiKVM devices via Zeroconf or user input, validates credentials/TOTP, pins SSL certificates via `cert_handler.py`, sets unique ID to hardware serial number, and writes `ConfigEntry`.
  2. `__init__.py`: Initializes `PiKVMConfigEntry` (`ConfigEntry[PiKVMDataUpdateCoordinator]`), assigns `entry.runtime_data = coordinator`, sets up platforms (`sensor`, `binary_sensor`), manages device registry, and handles device removal via `async_remove_config_entry_device`.
  3. `coordinator.py`: `PiKVMDataUpdateCoordinator` executes async polling of PiKVM `/api/info` endpoint using shared `aiohttp.ClientSession`. Raises translated exceptions (`ConfigEntryAuthFailed`, `UpdateFailed`) without duplicate error logs. Manages self-healing repairs for undervoltage and throttling issues.
  4. `entity.py`: Base entity class linking entities to coordinator telemetry and DeviceInfo.
  5. `sensor.py`: Numeric sensor platform with Long-Term Statistics (LTS) support (CPU temp, CPU util, memory util, fan speed, MSD storage) using `SensorEntityDescription` and `icons.json`.
  6. `binary_sensor.py`: Binary sensor platform for state flags (throttling, MSD enabled/drive, extra services) with dynamic state icons via `icons.json`.
  7. `diagnostics.py`: Redacted diagnostic data dumping for config entries and device registry entries.

## Feature Inventory
Every feature from the Survey phase and user request assigned to a milestone:
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Dead Code Elimination | Remove dead `sensors/` directory, `PiKVMBaseSensor`, and `lazy_import_sensors` | M1 | Survey / R2 |
| 2 | Utilities Strict Typing | Add complete type annotations to all functions in `utils.py` | M1 | Survey / R2 |
| 3 | Sensor Icon Translations | Remove hardcoded `icon=` from `sensor.py` to allow `icons.json` mapping | M2 | Survey / R1 |
| 4 | Binary Sensor Icon Translations | Remove hardcoded `icon=` and `_attr_icon` from `binary_sensor.py` for state icons | M2 | Survey / R1 |
| 5 | Entity Strict Typing & Final Attributes | Resolve `@final` overrides and complete type annotations in entity classes | M2 | Survey / R2 |
| 6 | Coordinator Exception Translations | Wire `ConfigEntryAuthFailed` & `UpdateFailed` to `translation_domain`, `key`, `placeholders` | M3 | Survey / R1 |
| 7 | Coordinator Log Cleanup | Eliminate premature `_LOGGER.error` before raising auth/connection exceptions | M3 | Survey / R1 |
| 8 | Coordinator Strict Typing | Annotate SSLContext, clean types, resolve all mypy strict errors in coordinator | M3 | Survey / R2 |
| 9 | Zeroconf Discovery Unique ID | Set `async_set_unique_id(serial)` & `_abort_if_unique_id_configured(updates={CONF_HOST: host})` | M4 | Survey / R1 |
| 10 | Options Flow Deprecation Fix | Remove deprecated `self.config_entry = config_entry` in `OptionsFlow.__init__` | M4 | Survey / R1 |
| 11 | Runtime Data Modernization | Define `PiKVMConfigEntry = ConfigEntry[PiKVMDataUpdateCoordinator]`, remove `hass.data[DOMAIN]` | M4 | Survey / R1 |
| 12 | Clean Config Entry Unloading | Use `cv.config_entry_only_config_schema(DOMAIN)`, remove redundant `async_unload_platforms` in remove entry | M4 | Survey / R1 |
| 13 | Stale Device Removal | Implement `async_remove_config_entry_device` callback in `__init__.py` | M4 | Survey / R1 |
| 14 | PEP 561 Marker | Add `custom_components/pikvm/py.typed` | M5 | Survey / R2 |
| 15 | Platinum Manifest Quality Scale | Set `"quality_scale": "platinum"` in `manifest.json` | M5 | Survey / R2 |
| 16 | 54-Rule Quality Scale Tracking | Populate all 54 rules in `quality_scale.yaml` (20 Bronze, 10 Silver, 21 Gold, 3 Platinum) | M5 | Survey / R1/R2 |
| 17 | Translation String Synchronization | Ensure `strings.json` and `translations/en.json` are valid JSON and fully synchronized | M5 | Survey / R1 |
| 18 | E2E & Unit Test Suite (100% Coverage) | Align tests with refactored entities, cover all 35 branches, achieve 100% coverage | M6 | Survey / R3 |
| 19 | Static Typing & Linting CI Enforcement | Pass `mypy --strict` and `ruff check` with 0 errors, enforce in `tests.yaml` and `requirements_test.txt` | M6 | Survey / R3 |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| E2E | E2E Test Suite | Create opaque-box requirement-driven test suite (Tiers 1-4) & TEST_READY.md | none | DONE |
| M1 | Legacy Code Elimination & Utils Typing | Delete `sensors/`, remove `PiKVMBaseSensor`, type `utils.py`, update legacy sensor unit tests | none | DONE |
| M2 | Entities & Icon Translations | Strip hardcoded icons from `sensor.py` and `binary_sensor.py`, defensive hardening, strict type entity classes | M1 | DONE |
| M3 | Coordinator & Exception Translations | Wire translated exceptions in `coordinator.py`, remove duplicate logging, strict type coordinator | M1 | DONE |
| M4 | Lifecycle, Discovery & Config Flow | Zeroconf `async_set_unique_id`, `PiKVMConfigEntry`, `runtime_data`, `async_remove_config_entry_device` | M1, M3 | DONE |
| M5 | Quality Scale Metadata & Manifest | Add `py.typed`, update `manifest.json`, populate all 54 rules in `quality_scale.yaml`, sync strings | M2, M3, M4 | DONE |
| M6 | Final Verification & CI Hardening | 100% statement & branch coverage, `mypy --strict`, `ruff check`, update `tests.yaml` and `requirements_test.txt` | E2E, M1-M5 | DONE |

## Interface Contracts
### `custom_components/pikvm/utils.py`
- `get_nested_value(data: Mapping[str, Any] | Any, path: Sequence[str] | str, default: Any = None) -> Any`
- `bytes_to_mb(value: int | float | None) -> float | None`
- `get_unique_id_base(host: str, port: int) -> str`
- `create_data_schema(defaults: Mapping[str, Any] | None = None) -> vol.Schema`
- `normalize_url(url: str) -> str`

### `custom_components/pikvm/__init__.py`
- `type PiKVMConfigEntry = ConfigEntry[PiKVMDataUpdateCoordinator]`
- `CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)`
- `async def async_setup_entry(hass: HomeAssistant, entry: PiKVMConfigEntry) -> bool`
- `async def async_unload_entry(hass: HomeAssistant, entry: PiKVMConfigEntry) -> bool`
- `async def async_remove_entry(hass: HomeAssistant, entry: PiKVMConfigEntry) -> None`
- `async def async_remove_config_entry_device(hass: HomeAssistant, config_entry: PiKVMConfigEntry, device_entry: dr.DeviceEntry) -> bool`

### `custom_components/pikvm/coordinator.py`
- Inherits `DataUpdateCoordinator[PiKVMData]`
- In `_async_update_data()`:
  - Raises `ConfigEntryAuthFailed(translation_domain=DOMAIN, translation_key="authentication_error")`
  - Raises `UpdateFailed(translation_domain=DOMAIN, translation_key="timeout", translation_placeholders={"host": self.clean_host})`
  - Raises `UpdateFailed(translation_domain=DOMAIN, translation_key="cannot_connect", translation_placeholders={"host": self.clean_host})`
  - Raises `UpdateFailed(translation_domain=DOMAIN, translation_key="communication_error", translation_placeholders={"host": self.clean_host, "error": str(err)})`

### `custom_components/pikvm/config_flow.py`
- In `async_step_zeroconf(self, discovery_info: ZeroconfServiceInfo) -> ConfigFlowResult`:
  - `await self.async_set_unique_id(serial)`
  - `self._abort_if_unique_id_configured(updates={CONF_HOST: host})`

## Code Layout
- `custom_components/pikvm/`
  - `__init__.py`: Component lifecycle, setup, unload, remove, device removal, `PiKVMConfigEntry`
  - `coordinator.py`: DataUpdateCoordinator, translated exceptions, repairs
  - `config_flow.py`: User, Zeroconf (native unique ID), Reauth, Reconfigure flows
  - `options_flow.py`: Scan interval options flow
  - `cert_handler.py`: Certificate fetching and SSLContext management
  - `entity.py`: Base entity class linking to coordinator telemetry
  - `sensor.py`: Numeric LTS sensors using `SENSOR_DESCRIPTIONS` and `icons.json`
  - `binary_sensor.py`: Binary state sensors using `BINARY_SENSOR_DESCRIPTIONS` and `icons.json`
  - `diagnostics.py`: Redacted diagnostic data dumping
  - `utils.py`: Strictly typed URL, schema, and data helpers
  - `strings.json` & `translations/en.json`: UI and exception translations
  - `icons.json`: MDI icon translations including dynamic state icons
  - `manifest.json`: Integration manifest with `"quality_scale": "platinum"`
  - `quality_scale.yaml`: Complete 54-rule quality scale tracking file
  - `py.typed`: PEP 561 typing marker
- `tests/`: Comprehensive unit and integration test suite targeting 100% coverage
- `.github/workflows/tests.yaml`: CI pipeline enforcing pytest 100% coverage, `mypy --strict`, and `ruff check`
