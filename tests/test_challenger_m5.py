"""Adversarial challenger tests for Milestone 5 (Quality Scale Metadata, Manifest & Strict Typing)."""

from __future__ import annotations

import json
import ssl
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml
from pikvm_aio import (
    PiKVMAuthenticationError,
    PiKVMConnectionError,
    PiKVMDeviceError,
    PiKVMTimeoutError,
)

from custom_components.pikvm import cert_handler
from custom_components.pikvm.const import DOMAIN

BASE_DIR = Path(__file__).resolve().parent.parent
COMPONENT_DIR = BASE_DIR / "custom_components" / "pikvm"


# -----------------------------------------------------------------------------
# Challenge 1: Adversarially Test quality_scale.yaml
# -----------------------------------------------------------------------------


def test_adversarial_quality_scale_rules_completeness():
    """Adversarially verify all 54 rules in quality_scale.yaml with strict schema."""
    bronze_rules = {
        "action-setup",
        "appropriate-polling",
        "brands",
        "common-modules",
        "config-flow",
        "config-flow-test-coverage",
        "dependency-transparency",
        "docs-actions",
        "docs-conditions",
        "docs-high-level-description",
        "docs-installation-instructions",
        "docs-removal-instructions",
        "docs-triggers",
        "entity-event-setup",
        "entity-unique-id",
        "has-entity-name",
        "runtime-data",
        "test-before-configure",
        "test-before-setup",
        "unique-config-entry",
    }
    silver_rules = {
        "action-exceptions",
        "config-entry-unloading",
        "docs-configuration-parameters",
        "docs-installation-parameters",
        "entity-unavailable",
        "integration-owner",
        "log-when-unavailable",
        "parallel-updates",
        "reauthentication-flow",
        "test-coverage",
    }
    gold_rules = {
        "devices",
        "diagnostics",
        "discovery",
        "discovery-update-info",
        "docs-data-update",
        "docs-examples",
        "docs-known-limitations",
        "docs-supported-devices",
        "docs-supported-functions",
        "docs-troubleshooting",
        "docs-use-cases",
        "dynamic-devices",
        "entity-category",
        "entity-device-class",
        "entity-disabled-by-default",
        "entity-translations",
        "exception-translations",
        "icon-translations",
        "reconfiguration-flow",
        "repair-issues",
        "stale-devices",
    }
    platinum_rules = {
        "async-dependency",
        "inject-websession",
        "strict-typing",
    }

    all_expected = bronze_rules | silver_rules | gold_rules | platinum_rules
    assert len(all_expected) == 54

    qs_path = COMPONENT_DIR / "quality_scale.yaml"
    assert qs_path.is_file(), "quality_scale.yaml must exist as a file"

    with qs_path.open(encoding="utf-8") as f:
        content = f.read()

    # Section comments must exist
    for section_header in ["# Bronze", "# Silver", "# Gold", "# Platinum"]:
        assert section_header in content, f"Missing section header: {section_header}"

    parsed = yaml.safe_load(content)
    assert isinstance(parsed, dict), "quality_scale.yaml root must be a dict"
    assert "rules" in parsed, "quality_scale.yaml must contain 'rules' key"

    rules = parsed["rules"]
    assert isinstance(rules, dict), "rules must be a dictionary"
    assert len(rules) == 54, f"Expected 54 rules, found {len(rules)}"

    missing = all_expected - set(rules.keys())
    extra = set(rules.keys()) - all_expected
    assert not missing, f"Missing rules in quality_scale.yaml: {missing}"
    assert not extra, f"Unexpected extra rules in quality_scale.yaml: {extra}"

    valid_statuses = {"done", "exempt"}
    for rule_name, rule_body in rules.items():
        if isinstance(rule_body, str):
            status = rule_body
            comment = None
        elif isinstance(rule_body, dict):
            status = rule_body.get("status")
            comment = rule_body.get("comment")
        else:
            pytest.fail(f"Invalid rule format for '{rule_name}': {rule_body}")

        assert status in valid_statuses, f"Rule '{rule_name}' has invalid status '{status}'"
        if status == "exempt":
            assert comment is not None, f"Exempt rule '{rule_name}' missing comment"
            assert isinstance(comment, str) and comment.strip(), f"Exempt rule '{rule_name}' has empty comment"


# -----------------------------------------------------------------------------
# Challenge 2: Adversarially Test manifest.json
# -----------------------------------------------------------------------------


def test_adversarial_manifest_platinum_compliance():
    """Adversarially verify manifest.json fields and quality_scale=platinum."""
    manifest_path = COMPONENT_DIR / "manifest.json"
    assert manifest_path.is_file(), "manifest.json must exist"

    with manifest_path.open(encoding="utf-8") as f:
        manifest = json.load(f)

    assert manifest.get("domain") == DOMAIN
    assert manifest.get("name") == "PiKVM"
    assert manifest.get("quality_scale") == "platinum", (
        f"Expected quality_scale 'platinum', got '{manifest.get('quality_scale')}'"
    )
    assert manifest.get("integration_type") == "device"
    assert manifest.get("iot_class") == "local_polling"
    assert manifest.get("config_flow") is True
    assert isinstance(manifest.get("codeowners"), list) and manifest["codeowners"]
    assert isinstance(manifest.get("requirements"), list)
    assert any("pikvm-aio" in req for req in manifest["requirements"])
    assert any("pyotp" in req for req in manifest["requirements"])


# -----------------------------------------------------------------------------
# Challenge 3: Adversarially Test PEP 561 py.typed
# -----------------------------------------------------------------------------


def test_adversarial_py_typed_file():
    """Verify PEP 561 py.typed marker file exists and is recognized."""
    py_typed = COMPONENT_DIR / "py.typed"
    assert py_typed.exists(), "py.typed does not exist"
    assert py_typed.is_file(), "py.typed is not a regular file"


# -----------------------------------------------------------------------------
# Challenge 4: Adversarially Fuzz cert_handler.py
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_adversarial_fuzz_fetch_serialized_cert(hass: Any):
    """Stress-test fetch_serialized_cert with hostile URLs and exceptions."""
    hostile_urls = [
        "",
        "   ",
        "http://",
        "https://",
        "ftp://example.com",
        "http://\x00invalid",
        "https://" + "a" * 1000 + ".local",
    ]
    for url in hostile_urls:
        with patch(
            "custom_components.pikvm.cert_handler.fetch_remote_cert",
            new=AsyncMock(side_effect=Exception("URL error")),
        ):
            res = await cert_handler.fetch_serialized_cert(hass, url)
            assert res is None

    # Hostile exceptions
    exceptions = [
        ValueError("bad input"),
        TypeError("bad type"),
        ssl.SSLError("ssl failure"),
        ConnectionResetError("reset"),
        OSError("os err"),
        RuntimeError("runtime"),
    ]
    for exc in exceptions:
        with patch(
            "custom_components.pikvm.cert_handler.fetch_remote_cert",
            new=AsyncMock(side_effect=exc),
        ):
            res = await cert_handler.fetch_serialized_cert(hass, "https://test.local")
            assert res is None


@pytest.mark.asyncio
async def test_adversarial_fuzz_is_pikvm_device_payloads(hass: Any):
    """Fuzz is_pikvm_device with hostile and unexpected device payloads."""
    payload_cases = [
        # (payload, exp_success, exp_serial, exp_model, exp_name)
        (None, True, "unknown", "PiKVM", "PiKVM"),
        ({}, True, "unknown", "PiKVM", "PiKVM"),
        ({"hw": None}, False, None, None, None),
        ({"hw": {"platform": None}}, False, None, None, None),
        ({"hw": {"platform": {"serial": "SN-999"}}}, True, "sn-999", "PiKVM", "PiKVM"),
        ({"hw": {"platform": {"serial": 8888}}}, True, "8888", "PiKVM", "PiKVM"),
        ("string-payload", True, "unknown", "PiKVM", "PiKVM"),
        (123456, True, "unknown", "PiKVM", "PiKVM"),
    ]

    for payload, exp_succ, exp_serial, exp_model, exp_name in payload_cases:
        with patch(
            "custom_components.pikvm.cert_handler.PiKVMClient.get_info",
            new=AsyncMock(return_value=payload),
        ):
            resp = await cert_handler.is_pikvm_device(hass, "https://test.local", "u", "p", "c")
            assert isinstance(resp, cert_handler.PiKVMResponse)
            if exp_succ:
                assert resp.success is True
                assert resp.serial == exp_serial
                assert resp.model == exp_model
                assert resp.name == exp_name
                assert resp.error is None
            else:
                assert resp.success is False
                assert resp.error == "cannot_connect"


@pytest.mark.asyncio
async def test_adversarial_fuzz_is_pikvm_device_null_ssl_context(hass: Any):
    """Test is_pikvm_device behavior when _DEFAULT_NO_VERIFY_SSL_CONTEXT is None."""
    mock_dev = MagicMock()
    mock_dev.serial = "PIKVM-SSL"
    mock_dev.model = "V3"
    mock_dev.name = "PiKVM SSL"

    with patch(
        "custom_components.pikvm.cert_handler._DEFAULT_NO_VERIFY_SSL_CONTEXT",
        None,
    ), patch(
        "custom_components.pikvm.cert_handler.PiKVMClient.get_info",
        new=AsyncMock(return_value=mock_dev),
    ):
        resp = await cert_handler.is_pikvm_device(hass, "https://test.local", "u", "p", "c")
        assert resp.success is True
        assert resp.serial == "pikvm-ssl"


@pytest.mark.asyncio
async def test_adversarial_fuzz_is_pikvm_device_exceptions(hass: Any):
    """Test is_pikvm_device translates all standard and unexpected exceptions safely."""
    cases = [
        (PiKVMAuthenticationError("auth failed"), "Exception_HTTP403"),
        (PiKVMTimeoutError("timed out"), "timeout"),
        (PiKVMConnectionError("conn refused"), "cannot_connect"),
        (PiKVMDeviceError("internal err"), "cannot_connect"),
        (RuntimeError("unexpected runtime error"), "cannot_connect"),
        (KeyError("missing key"), "cannot_connect"),
        (TypeError("type mismatch"), "cannot_connect"),
        (ssl.SSLError("ssl error"), "cannot_connect"),
    ]

    for exc, expected_error_key in cases:
        with patch(
            "custom_components.pikvm.cert_handler.PiKVMClient.get_info",
            new=AsyncMock(side_effect=exc),
        ):
            resp = await cert_handler.is_pikvm_device(hass, "https://test.local", "u", "p", "c")
            assert resp.success is False
            assert resp.error == expected_error_key
            assert resp.serial is None
            assert resp.model is None
