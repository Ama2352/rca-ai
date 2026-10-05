"""Operational safety checks for the live release-regression runner."""

from scripts.run_release_regression import audit_secret_leak, frozen_contract_hashes


def test_release_runner_checks_all_frozen_prompt_and_schema_hashes():
    assert frozen_contract_hashes() == {
        "generator_prompt": "2902e2200777ea4731cd0baaf9cff616e9ee637c0a1344202fbc9d32607c98de",
        "generator_schema": "26df3bd25892a50bdad1859b31d1a3fe1dd35fdf92f15fce9954d25abcc10119",
        "validator_prompt": "1b61f29d658c079b27b18ca0d0ea3e59b96e3989f21eef0368d9a1d17c86e6b6",
        "validator_schema": "3fc8c2fe12d2748fc934cfe3ae0bd50ca0db1a13891d71df7922d1e6daeebc06",
    }


def test_secret_audit_detects_only_actual_file_content_leaks(tmp_path):
    artifact = tmp_path / "safe.json"
    artifact.write_text('{"status":"ok"}', encoding="utf-8")
    assert audit_secret_leak(tmp_path, "test-secret") is False
    artifact.write_text('{"accidental":"test-secret"}', encoding="utf-8")
    assert audit_secret_leak(tmp_path, "test-secret") is True
