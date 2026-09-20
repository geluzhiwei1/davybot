# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

import sys


def test_ensure_acp_sdk_path_uses_env_override(monkeypatch, tmp_path):
    from dawei.acp import sdk_loader

    fake_src = tmp_path / "python-sdk" / "src"
    fake_pkg = fake_src / "acp"
    fake_pkg.mkdir(parents=True)
    (fake_pkg / "__init__.py").write_text('VALUE = "ok"\n', encoding="utf-8")

    monkeypatch.setenv("DAWEI_ACP_SDK_PATH", str(fake_src))

    resolved = sdk_loader.ensure_acp_sdk_path()
    assert resolved == fake_src.resolve()
    assert str(fake_src.resolve()) in sys.path


def test_import_acp_from_local_sdk(monkeypatch, tmp_path):
    from dawei.acp import sdk_loader

    fake_src = tmp_path / "python-sdk" / "src"
    fake_pkg = fake_src / "acp"
    fake_pkg.mkdir(parents=True)
    (fake_pkg / "__init__.py").write_text('VALUE = "from_local_sdk"\n', encoding="utf-8")

    monkeypatch.setenv("DAWEI_ACP_SDK_PATH", str(fake_src))
    sys.modules.pop("acp", None)

    module = sdk_loader.import_acp()

    assert getattr(module, "VALUE", None) == "from_local_sdk"
