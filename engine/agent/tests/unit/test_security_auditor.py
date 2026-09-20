# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Unit tests for the SecurityAuditor (P0, domain 12)."""

import json
from pathlib import Path

from dawei.core.security_auditor import SecurityAuditor, _redact


def _read_lines(path: Path) -> list[dict]:
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").strip().splitlines()]


def test_writes_jsonl_record(tmp_path: Path):
    log = tmp_path / "audit.jsonl"
    aud = SecurityAuditor(log_path=log)
    aud.log("security.policy.change", user_id="u1", scope="user", settings={"a": 1})
    recs = _read_lines(log)
    assert len(recs) == 1
    assert recs[0]["event"] == "security.policy.change"
    assert recs[0]["user_id"] == "u1"
    assert recs[0]["settings"] == {"a": 1}
    assert recs[0]["ts"].endswith("+00:00")  # UTC


def test_redacts_sensitive_keys():
    out = _redact(
        {"enableCommandWhitelist": True, "api_key": "sk-x", "password": "p", "nested": {"token": "t"}}
    )
    assert out["enableCommandWhitelist"] is True
    assert out["api_key"] == "***REDACTED***"
    assert out["password"] == "***REDACTED***"
    assert out["nested"]["token"] == "***REDACTED***"


def test_disabled_is_silent(tmp_path: Path):
    log = tmp_path / "audit.jsonl"
    aud = SecurityAuditor(log_path=log, enabled=False)
    aud.log("x")
    assert not log.exists() or log.read_text() == ""


def test_does_not_raise_on_bad_path(tmp_path: Path):
    aud = SecurityAuditor(log_path=Path("/nonexistent_root_xyz/a/b.jsonl"))
    aud.log("x")  # must not raise


def test_append_multiple(tmp_path: Path):
    log = tmp_path / "audit.jsonl"
    aud = SecurityAuditor(log_path=log)
    for i in range(3):
        aud.log("e", i=i)
    assert len(_read_lines(log)) == 3
