#!/usr/bin/env python3
"""Connector 包校验器(单文件 connector.yml 格式)。

结构:
  platform / display_name / version
  capability: {publish, publish_modes[], trending, metrics}
  constraints: {char_limit, max_files, max_video_seconds, rich_text}
  domains: [导航白名单]
  publish: {compose_url, selectors{...}, login_check?, rich_text?}
  trending?: {url, container, topic, pagination}
  metrics?: {指标名: 选择器}

安全约束:包内仅声明式资产(connector.yml + adapt.md),禁止可执行文件。
退出码 0 通过 / 1 失败。PyYAML 优先,极简解析兜底(biz1 零依赖)。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FORBIDDEN_SUFFIXES = {".py", ".pyc", ".sh", ".exe", ".dll", ".so", ".bat", ".ps1", ".js"}
PLATFORM_RE = re.compile(r"^[a-z][a-z0-9_]*$")
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")

ENUMS = {
    "publish": {"api", "browser", "none"},
    "trending": {"api", "browser", "none"},
    "metrics": {"api", "browser", "none"},
}
SELECTOR_GROUPS = {"compose_box", "publish_button", "save_draft_button", "title_input",
                   "media_upload", "success_indicator", "compose_button"}


def load_yaml(path: Path) -> dict:
    try:
        import yaml

        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except ImportError:
        return _mini_yaml(path.read_text(encoding="utf-8")) or {}


def _mini_yaml(text: str) -> dict:
    import ast

    data: dict = {}
    stack: list[tuple[int, dict]] = [(-1, data)]
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        line = raw.strip()
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key, value = key.strip(), value.strip()
        if value == "":
            child: dict = {}
            parent[key] = child
            stack.append((indent, child))
        else:
            if value and value[0] in "[{":
                try:
                    value = ast.literal_eval(value)
                except (ValueError, SyntaxError):
                    inner = value.strip("[]{}")
                    value = [v.strip().strip("'\"") for v in inner.split(",") if v.strip()]
            parent[key] = value
    return data


def fail(msgs: list[str], msg: str) -> None:
    msgs.append(msg)


def validate_package(pkg_dir: Path) -> list[str]:
    msgs: list[str] = []
    platform = pkg_dir.name

    if not PLATFORM_RE.match(platform):
        fail(msgs, f"[{platform}] bad platform slug")

    cf = pkg_dir / "connector.yml"
    if not cf.exists():
        fail(msgs, f"[{platform}] missing connector.yml")
        return msgs

    for f in pkg_dir.rglob("*"):  # 供应链:声明式资产-only
        if f.is_file() and f.suffix.lower() in FORBIDDEN_SUFFIXES:
            fail(msgs, f"[{platform}] forbidden executable: {f.name}")

    pkg = load_yaml(cf)

    for field in ("platform", "display_name", "version"):
        if field not in pkg:
            fail(msgs, f"[{platform}] missing {field}")
    if pkg.get("platform") != platform:
        fail(msgs, f"[{platform}] platform mismatch: {pkg.get('platform')}")
    if not SEMVER_RE.match(str(pkg.get("version", ""))):
        fail(msgs, f"[{platform}] version must be semver: {pkg.get('version')}")

    cap = pkg.get("capability") or {}
    for field, allowed in ENUMS.items():
        if field in cap and cap[field] not in allowed:
            fail(msgs, f"[{platform}] capability.{field} invalid: {cap[field]}")
    modes = cap.get("publish_modes") or []
    if not isinstance(modes, list) or any(m not in ("direct", "draft_box") for m in modes):
        fail(msgs, f"[{platform}] capability.publish_modes invalid: {modes}")

    domains = pkg.get("domains") or []
    if not isinstance(domains, list):
        fail(msgs, f"[{platform}] domains must be a list")

    pub = pkg.get("publish") or {}
    if cap.get("publish") == "browser":
        compose_url = str(pub.get("compose_url", ""))
        if not compose_url:
            fail(msgs, f"[{platform}] browser publish requires publish.compose_url")
        sels = pub.get("selectors") or {}
        if not (sels.get("compose_box") or sels.get("compose_button")):
            fail(msgs, f"[{platform}] publish.selectors missing compose_box/compose_button")
        if not sels.get("success_indicator"):
            fail(msgs, f"[{platform}] publish.selectors missing success_indicator (BX-3)")
        if domains and compose_url:
            host = re.sub(r"^https?://", "", compose_url).split("/")[0].split(":")[0]
            if not any(str(d) == host for d in domains if d):
                fail(msgs, f"[{platform}] compose_url host not in domains: {host}")

    unknown_groups = set(pub.get("selectors") or {}) - SELECTOR_GROUPS
    if unknown_groups:
        fail(msgs, f"[{platform}] unknown selector groups: {sorted(unknown_groups)}")

    tv = pkg.get("trending")
    if tv and cap.get("trending") == "none":
        fail(msgs, f"[{platform}] trending section present but capability.trending=none")
    return msgs


def validate_rule_pack(path: Path) -> list[str]:
    """规则包 pack.yml 校验(结构/枚举/正则可编译,与 rule_pack_loader 同规)。"""
    msgs: list[str] = []
    pkg = load_yaml(path)
    pack_id = str(pkg.get("pack_id", "")).strip()
    tag = pack_id or path.parent.name

    for field in ("pack_id", "name", "layer", "version", "rules"):
        if field not in pkg:
            fail(msgs, f"[{tag}] missing {field}")
    if pkg.get("layer") not in {"universal", "industry", "brand"}:
        fail(msgs, f"[{tag}] layer invalid: {pkg.get('layer')}")
    if not SEMVER_RE.match(str(pkg.get("version", ""))):
        fail(msgs, f"[{tag}] version must be semver: {pkg.get('version')}")
    rules = pkg.get("rules")
    if not isinstance(rules, list) or not rules:
        fail(msgs, f"[{tag}] rules must be a non-empty list")
        return msgs
    for i, r in enumerate(rules):
        if not isinstance(r, dict) or not all(r.get(k) for k in ("id", "pattern", "citation")):
            fail(msgs, f"[{tag}] rules[{i}] missing id/pattern/citation")
            continue
        try:
            re.compile(str(r["pattern"]))
        except re.error as e:
            fail(msgs, f"[{tag}] rules[{i}].pattern invalid regex: {e}")
    return msgs


def validate_rule_packs(root: Path) -> list[str]:
    msgs: list[str] = []
    for path in sorted(root.glob("**/pack.yml")):
        msgs.extend(validate_rule_pack(path))
    if not msgs and not list(root.glob("**/pack.yml")):
        msgs.append(f"[rule-packs] no pack.yml found under {root}")
    return msgs


def validate_team_package(root: Path) -> list[str]:
    """团队包校验:team.yml 必备字段 + 引用存在 + 供应链(无可执行)。"""
    msgs: list[str] = []
    team_yml = root / "team.yml"
    if not team_yml.is_file():
        return [f"[{root.name}] missing team.yml"]
    team = load_yaml(team_yml)
    for field in ("name", "agents", "skills"):
        if field not in team or not team[field]:
            fail(msgs, f"[{root.name}] missing/empty {field}")
    for agent_id in team.get("agents") or []:
        if not (root / "agents" / str(agent_id) / "agent.yml").is_file():
            fail(msgs, f"[{root.name}] agent definition missing: {agent_id}")
    for skill_id in team.get("skills") or []:
        if not (root / "skills" / str(skill_id) / "skill.yml").is_file():
            fail(msgs, f"[{root.name}] skill definition missing: {skill_id}")
    for f in root.rglob("*"):  # 供应链:声明式资产-only
        if f.is_file() and f.suffix.lower() in FORBIDDEN_SUFFIXES:
            fail(msgs, f"[{root.name}] forbidden executable: {f.name}")
    return msgs


def main() -> int:
    root = HERE.parent
    targets = sorted(d for d in root.iterdir() if d.is_dir() and not d.name.startswith(("_", ".")))
    if len(sys.argv) > 1:
        targets = [root / a for a in sys.argv[1:]]
    if not targets:
        print("no connector packages found")
        return 0

    all_msgs: list[str] = []
    for pkg in targets:
        all_msgs.extend(validate_package(pkg))

    # 规则包(market-packages/rule-packs,与 connectors 同通道发布 biz1)
    rule_root = root.parent / "rule-packs"
    if rule_root.is_dir():
        all_msgs.extend(validate_rule_packs(rule_root))

    # 团队包(market-packages/teams/*,E4)
    teams_root = root.parent / "teams"
    if teams_root.is_dir():
        for team_dir in sorted(d for d in teams_root.iterdir() if d.is_dir()):
            all_msgs.extend(validate_team_package(team_dir))

    result = {"valid": not all_msgs, "packages": [p.name for p in targets]}
    if all_msgs:
        result["errors"] = all_msgs
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if all_msgs else 0


if __name__ == "__main__":
    sys.exit(main())
