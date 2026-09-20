# MarketingAgent 编排 E2E(进程内,复刻生产链路):
#   local_context JWT(set_gateway_token 同源)→ 网关 LLM(llm-pricing 目录模型)
#   → mkt-orchestrator mode → market 工具真实调用 → 最终回答
# 运行:export PYTHONUTF8=1 && .venv/Scripts/python.exe scripts_e2e_market_agent.py <token> [mode] [question]
import asyncio
import sys
import tempfile

TOKEN = open("C:/Users/zhglz/.market_e2e_token.txt").read().strip() if len(sys.argv) < 2 else sys.argv[1]
MODE = sys.argv[2] if len(sys.argv) > 2 else "mkt-orchestrator"
QUESTION = sys.argv[3] if len(sys.argv) > 3 else "萤火最近在 AI 回答里的引用率怎么样?哪些关键词没被引用?给我数据结论。"
MODEL = "glm-5.3"

TOOL_CALLS: list = []


async def main():
    from dawei.core import local_context

    local_context.set_auth_token(TOKEN)

    from dawei import get_dawei_home
    from dawei.llm_api import LLMProvider

    provider = LLMProvider(workspace_root=str(get_dawei_home()))
    provider.set_gateway_token(TOKEN)
    ok = provider.set_current_config(MODEL)
    print(f"[E2E] gateway config '{MODEL}' registered: {ok}")

    # trace 工具→API 真实调用(模块全局查找点可 monkeypatch)
    from dawei.tools.custom_tools import market_tools as mt

    orig = mt._call_market

    async def traced(method, path, **kw):
        TOOL_CALLS.append((method, path, dict(kw.get("params") or {})))
        return await orig(method, path, **kw)

    mt._call_market = traced

    from dawei.agentic.agent_execution_service import agent_execution_service
    from dawei.workspace.user_workspace import UserWorkspace

    ws_dir = tempfile.mkdtemp(prefix="mkt-agent-e2e-")
    workspace = UserWorkspace(ws_dir)
    await workspace.initialize()

    result = await agent_execution_service.execute_agent_task(
        workspace=workspace,
        message=QUESTION,
        session_id="mkt-e2e-s1",
        task_id="mkt-e2e-t1",
        task_type="user",
        llm=MODEL,
        mode=MODE,
    )

    print("\n=== 工具调用轨迹(真实 prod market API) ===")
    for m, p, params in TOOL_CALLS:
        print(f"  {m} {p} {params or ''}")
    if not TOOL_CALLS:
        print("  (无工具调用!)")

    print("\n=== final_output ===")
    print(result.get("final_output") or "(empty)")
    print("\n=== keys ===", sorted(result.keys()))


asyncio.run(main())
