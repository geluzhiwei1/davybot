# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""
IP 模块联调测试脚本 (P4-11 / P4-16 / P4-24)

测试后端 IP API 端点：
  - POST /api/team/{slug}/run — 8个模块任务提交
  - GET /api/ip/{module}/{taskId} — 任务结果轮询
  - IP 模块 CRUD/导出端点
  - 文件上传端点
  - 许可证管理端点

运行方式:
    # 启动后端
    cd agent && uv run dawei server start --port 8010

    # 在另一个终端运行
    # 方式1: 全量测试
    uv run python -m pytest tests/test_ip_integration.py -v -s

    # 方式2: 运行指定模块测试
    uv run python -m pytest tests/test_ip_integration.py -v -k test_m1

    # 方式3: 运行许可证测试
    uv run python -m pytest tests/test_ip_integration.py -v -k test_license
"""

import pytest
import httpx
import time
from typing import Any, Dict

# ─── 配置 ───

BASE_URL = "http://localhost:8010"
API = httpx.AsyncClient(base_url=BASE_URL, timeout=httpx.Timeout(30))


# ─── Fixtures ───


@pytest.fixture(autouse=True)
async def _cleanup():
    yield
    # No cleanup needed for mock endpoints


async def _post(path: str, json: dict | None = None) -> dict:
    resp = await API.post(path, json=json)
    assert resp.status_code == 200, f"POST {path} failed: {resp.status_code} {resp.text}"
    return resp.json()


async def _get(path: str) -> dict:
    resp = await API.get(path)
    assert resp.status_code == 200, f"GET {path} failed: {resp.status_code} {resp.text}"
    return resp.json()


async def _poll(path: str, max_retries: int = 30) -> dict:
    """轮询任务结果"""
    for _ in range(max_retries):
        resp = await API.get(path)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("success") and data.get("data"):
                return data
        if resp.status_code == 404:
            time.sleep(0.5)
            continue
        resp.raise_for_status()
        time.sleep(0.5)
    raise TimeoutError(f"Task polling timeout: {path}")


# ================================================================
# M1 — 可专利性评估
# ================================================================


@pytest.mark.integration
async def test_m1_evaluate_idea():
    """M1: 提交技术描述并获取可专利性评估结果"""
    payload = {
        "description": "一种基于分布式架构的智能数据处理方法",
        "files": [],
    }
    submit = await _post("/api/team/ip-idea-vault/run", payload)
    task_id = submit["taskId"]
    assert task_id is not None

    result = await _poll(f"/api/ip/evaluate/{task_id}")
    assert result["success"] is True
    data = result["data"]

    # 验证核心字段
    assert "patentabilityScore" in data
    assert data["patentabilityScore"] > 0
    assert "noveltyAnalysis" in data
    assert "inventiveness" in data
    assert "industrialApplicability" in data
    assert "recommendedStrategy" in data
    assert data["status"] == "completed"

    print(f"  [M1 OK] Score: {data['patentabilityScore']}, Strategy: {data['recommendedStrategy']}")


# ================================================================
# M2 — 交底书生成
# ================================================================


@pytest.mark.integration
async def test_m2_generate_disclosure():
    """M2: 生成交底书并验证章节结构"""
    payload = {"description": "一种分布式智能数据处理系统"}
    submit = await _post("/api/team/ip-disclosure/run", payload)
    task_id = submit["taskId"]

    result = await _poll(f"/api/ip/disclosure/{task_id}")
    data = result["data"]

    assert data["title"] is not None
    assert data["status"] == "completed"
    assert "sections" in data

    sections = data["sections"]
    expected_sections = ["technicalField", "backgroundArt", "technicalProblem", "technicalSolution", "beneficialEffects", "embodiments", "drawings", "claims"]
    for section in expected_sections:
        assert section in sections, f"Missing section: {section}"
        assert sections[section]["content"] != ""

    print(f"  [M2 OK] Title: {data['title']}, Sections: {len(sections)}")

    # 测试章节更新
    update = await API.put(
        f"/api/ip/disclosure/{data['id']}/sections/technicalField",
        json={"content": "Updated content"}
    )
    assert update.status_code == 200

    # 测试导出
    export = await API.get(f"/api/ip/disclosure/{data['id']}/export")
    assert export.status_code == 200
    export_data = export.json()
    assert export_data["success"] is True


# ================================================================
# M3 — 智能撰写
# ================================================================


@pytest.mark.integration
async def test_m3_generate_draft():
    """M3: 生成专利申请文件并验证权利要求"""
    payload = {
        "disclosureId": "discl-test-001",
        "targetCountry": "CN",
        "strategy": "broad",
    }
    submit = await _post("/api/team/ip-draft/run", payload)
    task_id = submit["taskId"]

    result = await _poll(f"/api/ip/draft/{task_id}")
    data = result["data"]

    assert data["targetCountry"] == "CN"
    assert data["status"] == "completed"
    assert len(data["claims"]) > 0

    # 验证独立权利要求存在
    independent_claims = [c for c in data["claims"] if c["type"] == "independent"]
    assert len(independent_claims) >= 1

    print(f"  [M3 OK] Title: {data['title']}, Claims: {len(data['claims'])}")

    # 测试导出
    export = await API.get(f"/api/ip/draft/{data['id']}/export?format=docx")
    assert export.status_code == 200


@pytest.mark.integration
async def test_m3_multi_country_spawn():
    """M3 F3-10: 测试多国版本一键生成"""
    resp = await _post("/api/ip/draft/draft-test-001/spawn/US")
    assert resp["success"] is True
    assert "taskId" in resp["data"]
    print(f"  [M3 Multi-Country OK] Spawned US draft: {resp['data']['taskId']}")


# ================================================================
# M4 — 全球申请管家
# ================================================================


@pytest.mark.integration
async def test_m4_analyze_filing():
    """M4: 分析申请策略并验证 PCT 时间线"""
    payload = {
        "draftId": "draft-test-001",
        "targetMarkets": ["US", "EP", "JP"],
        "path": "pct",
    }
    submit = await _post("/api/team/ip-filing/run", payload)
    task_id = submit["taskId"]

    result = await _poll(f"/api/ip/filing/{task_id}")
    data = result["data"]

    assert data["status"] == "completed"
    assert data["recommendedPath"] == "PCT"
    assert "pathComparison" in data
    assert len(data["targetMarkets"]) == 3
    assert len(data["pctTimeline"]) > 0

    # 验证PCT 6个阶段
    pct_stages = [s["stage"] for s in data["pctTimeline"]]
    assert "RO" in pct_stages
    assert "NP" in pct_stages

    print(f"  [M4 OK] Path: {data['recommendedPath']}, Markets: {data['targetMarkets']}")


# ================================================================
# M5 — OA 答复
# ================================================================


@pytest.mark.integration
async def test_m5_analyze_oa():
    """M5: 分析OA通知书并验证答复策略"""
    payload = {"draftId": "draft-001", "country": "CN"}
    submit = await _post("/api/team/ip-oa-reply/run", payload)
    task_id = submit["taskId"]

    result = await _poll(f"/api/ip/oa-reply/{task_id}")
    data = result["data"]

    assert data["country"] == "CN"
    assert data["status"] == "completed"
    assert len(data["rejections"]) > 0
    assert data["recommendedStrategy"] != ""
    assert len(data["replies"]) > 0
    assert len(data["amendedClaims"]) > 0

    print(f"  [M5 OK] Strategy: {data['recommendedStrategy']}, Rejections: {len(data['rejections'])}")


# ================================================================
# M6 — 侵权雷达
# ================================================================


@pytest.mark.integration
async def test_m6_reverse_detection():
    """M6: 反向侵权探测"""
    payload = {
        "myTechDescription": "一种分布式智能数据处理方法，基于机器学习预测模型进行资源调度",
        "myPatentNumbers": ["CN20231000001.X"],
        "targetMarkets": ["CN", "US"],
    }
    submit = await _post("/api/team/ip-reverse-detection/run", payload)
    task_id = submit["taskId"]

    result = await _poll(f"/api/ip/reverse-detection/{task_id}")
    data = result["data"]

    assert data["type"] == "reverse_patent"
    assert len(data["results"]) > 0
    assert data["results"][0]["infringementProbability"] in ("high", "medium", "low")

    first_result = data["results"][0]
    print(f"  [M6 OK] Result: {first_result['infringerName']}, Probability: {first_result['infringementProbability']}")

    # 测试证据包导出
    alert_id = first_result["alert"]["id"]
    evidence = await API.get(f"/api/ip/reverse-detection/{data['id']}/evidence/{alert_id}")
    assert evidence.status_code == 200

    # 测试警告函导出
    warning = await API.get(f"/api/ip/reverse-detection/{data['id']}/warning/{alert_id}")
    assert warning.status_code == 200


# ================================================================
# M7 — 资产仪表盘
# ================================================================


@pytest.mark.integration
async def test_m7_analyze_portfolio():
    """M7: 资产组合分析"""
    submit = await _post("/api/team/ip-portfolio/run", {})
    task_id = submit["taskId"]

    result = await _poll(f"/api/ip/portfolio/{task_id}")
    data = result["data"]

    assert data["status"] == "completed"
    assert len(data["patents"]) > 0
    assert data["healthScore"] > 0
    assert "healthSubScores" in data
    assert "kpis" in data
    assert "competitors" in data
    assert "renewals" in data

    print(f"  [M7 OK] Health: {data['healthScore']}, Patents: {len(data['patents'])}, Competitors: {len(data['competitors'])}")

    # 测试报告导出
    export = await API.get(f"/api/ip/portfolio/{data['id']}/export?format=pdf")
    assert export.status_code == 200


# ================================================================
# M8 — 商标注册
# ================================================================


@pytest.mark.integration
async def test_m8_trademark_registration():
    """M8: 商标分类规划 + 可注册性预检"""
    payload = {
        "name": "DavBot",
        "businessScope": "计算机软件开发与销售",
    }
    submit = await _post("/api/team/ip-trademark/run", payload)
    task_id = submit["taskId"]

    result = await _poll(f"/api/ip/trademark/{task_id}")
    data = result["data"]

    assert data["name"] == "DavBot"
    assert data["status"] == "completed"
    assert len(data["recommendedClasses"]) > 0
    assert data["registrability"]["overallScore"] > 0

    # 验证分类类型
    class_types = {c["type"] for c in data["recommendedClasses"]}
    assert "core" in class_types, "Should have core classes"

    print(f"  [M8 OK] Classes: {len(data['recommendedClasses'])}, Registrability: {data['registrability']['overallScore']}")

    # 测试导出
    tid = data["id"]
    for endpoint in [f"/api/ip/trademark/{tid}/goods-list", f"/api/ip/trademark/{tid}/package", f"/api/ip/trademark/{tid}/material"]:
        resp = await API.get(endpoint)
        assert resp.status_code == 200


# ================================================================
# 文件上传
# ================================================================


@pytest.mark.integration
async def test_file_upload():
    """测试 IP 文件上传"""
    import io

    # 创建测试文件
    content = b"This is a test patent disclosure document."
    files = {"file": ("test-disclosure.txt", io.BytesIO(content), "text/plain")}

    resp = await API.post("/api/ip/upload", files=files)
    assert resp.status_code == 200
    data = resp.json()

    assert data["success"] is True
    assert "fileId" in data["data"]
    assert data["data"]["filename"] == "test-disclosure.txt"
    assert data["data"]["size"] == len(content)

    print(f"  [Upload OK] fileId: {data['data']['fileId']}")


# ================================================================
# 错误处理
# ================================================================


@pytest.mark.integration
async def test_invalid_team_slug():
    """测试无效 team slug 返回 404"""
    resp = await API.post("/api/team/invalid-team-slug/run", json={})
    assert resp.status_code == 404


@pytest.mark.integration
async def test_task_not_found():
    """测试不存在的 taskId 返回 404"""
    resp = await API.get("/api/ip/evaluate/nonexistent-task-uuid")
    assert resp.status_code == 404


@pytest.mark.integration
async def test_invalid_country_spawn():
    """测试无效国家代码返回 400"""
    resp = await API.post("/api/ip/draft/test-draft/spawn/INVALID")
    assert resp.status_code == 400


# ================================================================
# 许可证管理
# ================================================================


@pytest.mark.integration
async def test_license_activate_and_verify():
    """完整许可证流程: 激活 → 验证 → 续期 → 信息查询"""
    # 1. 激活
    activate_resp = await _post("/api/license/activate", {
        "license_key": "DVBYT-ENT-A001-B002-C003",
        "machine_id": "TEST-MACHINE-UUID-12345",
        "product": "normnomos-enterprise",
    })
    assert activate_resp["success"] is True
    assert activate_resp["token"] is not None
    assert len(activate_resp["features"]) > 0
    assert "ip-module" in activate_resp["features"]

    token = activate_resp["token"]

    # 2. 验证
    verify_resp = await _post("/api/license/verify", {
        "token": token,
        "machine_id": "TEST-MACHINE-UUID-12345",
    })
    assert verify_resp["valid"] is True
    assert verify_resp["remaining_days"] > 0

    # 3. 续期
    renew_resp = await _post("/api/license/renew", {
        "token": token,
        "extension_days": 365,
    })
    assert renew_resp["success"] is True
    new_token = renew_resp["token"]

    # 4. 信息查询
    info_resp = await _get(f"/api/license/info?token={new_token}")
    assert info_resp["is_active"] is True

    print(f"  [License OK] Features: {activate_resp['features']}, Expires: {activate_resp['expires_at']}")

    # 5. 吊销
    revoke_resp = await _post("/api/license/revoke", {
        "token": new_token,
        "reason": "test revoke",
    })
    assert revoke_resp["success"] is True


@pytest.mark.integration
async def test_license_invalid_key():
    """测试无效许可证密钥"""
    resp = await _post("/api/license/activate", {
        "license_key": "INVALID-KEY-FORMAT",
        "machine_id": "test-machine",
        "product": "normnomos-enterprise",
    })
    assert resp["success"] is False
    assert resp["error_code"] == "INVALID_KEY_FORMAT"


@pytest.mark.integration
async def test_license_wrong_machine():
    """测试机器ID不匹配"""
    activate_resp = await _post("/api/license/activate", {
        "license_key": "DVBYT-ENT-D001-E002-F003",
        "machine_id": "ORIGINAL-MACHINE-01",
        "product": "normnomos-enterprise",
    })
    token = activate_resp["token"]

    verify_resp = await _post("/api/license/verify", {
        "token": token,
        "machine_id": "DIFFERENT-MACHINE-02",
    })
    assert verify_resp["valid"] is False
    assert verify_resp["error_code"] == "MACHINE_MISMATCH"


# ================================================================
# 批量运行入口
# ================================================================


if __name__ == "__main__":
    import asyncio

    async def _run_all():
        print("=" * 60)
        print(" DavyBot IP Module — Integration Tests")
        print("=" * 60)
        print(f"  Base URL: {BASE_URL}")
        print()

        tests = [
            ("M1 可专利性评估", test_m1_evaluate_idea),
            ("M2 交底书生成", test_m2_generate_disclosure),
            ("M3 智能撰写", test_m3_generate_draft),
            ("M3 多国生成", test_m3_multi_country_spawn),
            ("M4 申请管家", test_m4_analyze_filing),
            ("M5 OA答复", test_m5_analyze_oa),
            ("M6 侵权雷达", test_m6_fto_check),
            ("M7 资产仪表盘", test_m7_analyze_portfolio),
            ("M8 商标注册", test_m8_trademark_registration),
            ("文件上传", test_file_upload),
            ("错误处理-无效slug", test_invalid_team_slug),
            ("错误处理-任务未找到", test_task_not_found),
            ("错误处理-无效国家", test_invalid_country_spawn),
            ("许可证-激活验证", test_license_activate_and_verify),
            ("许可证-无效密钥", test_license_invalid_key),
            ("许可证-机器不匹配", test_license_wrong_machine),
        ]

        passed = 0
        failed = 0

        for name, test_fn in tests:
            try:
                await test_fn()
                passed += 1
                print(f"  [PASS] {name}")
            except Exception as e:
                failed += 1
                print(f"  [FAIL] {name}: {e}")

        print()
        print(f"  Results: {passed} passed, {failed} failed, {len(tests)} total")
        if failed > 0:
            print("  Some tests FAILED!")
            exit(1)
        else:
            print("  All tests PASSED!")

    asyncio.run(_run_all())
