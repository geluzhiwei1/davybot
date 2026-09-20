# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""DavyBot IP SDK — HTTP client for the 8-module IP REST API.

Minimal async Python client. Depends only on httpx.
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

import httpx

from .models import (
    DisclosureResultResponse,
    DraftResultResponse,
    ExportInfo,
    FileUploadResult,
    FilingResultResponse,
    IdeaItem,
    IdeaResultResponse,
    InfringementResultResponse,
    IpDisclosure,
    IpDraft,
    IpFiling,
    IpInfringement,
    IpOaRecord,
    IpPortfolio,
    IpTrademark,
    OaReplyResultResponse,
    PortfolioResultResponse,
    TaskResponse,
    TrademarkResultResponse,
)


class _ModuleClient:
    """Base for per-module clients."""

    def __init__(self, parent: IpClient, module_slug: str):
        self._parent = parent
        self._slug = module_slug

    async def _submit(self, params: dict[str, Any]) -> TaskResponse:
        """Submit a task and return the task response."""
        data = await self._parent._post(f"/api/team/{self._slug}/run", json=params)
        return TaskResponse(task_id=data["taskId"])

    async def _poll(self, module_path: str, task_id: str, poll_interval: float = 1.0, timeout: float = 120) -> dict[str, Any]:
        """Poll for task result. Returns raw data dict on success."""
        url = f"/api/ip/{module_path}/{task_id}"
        deadline = time.monotonic() + timeout
        last_error = None
        while time.monotonic() < deadline:
            try:
                resp = await self._parent._get(url)
                if resp.get("success") and resp.get("data"):
                    return resp["data"]
                if resp.get("data", {}).get("status") == "failed":
                    raise RuntimeError(f"Task failed: {resp}")
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    # Task not ready yet — retry
                    last_error = e
                    await self._parent._sleep(poll_interval)
                    continue
                raise
            await self._parent._sleep(poll_interval)
        raise TimeoutError(f"Task {task_id} did not complete within {timeout}s. Last error: {last_error}")


class IdeaVaultClient(_ModuleClient):
    """M1 创意保护舱 client."""

    def __init__(self, parent: IpClient):
        super().__init__(parent, "ip-idea-vault")

    async def evaluate(self, description: str, files: list[str] | None = None) -> TaskResponse:
        """提交可专利性评估任务。

        Args:
            description: 技术方案描述
            files: 上传文件ID列表（可选）
        """
        params: dict[str, Any] = {"description": description}
        if files:
            params["files"] = files
        return await self._submit(params)

    async def get_result(self, task_id: str, timeout: float = 120) -> IdeaItem:
        """获取可专利性评估结果。"""
        data = await self._poll("evaluate", task_id, timeout=timeout)
        return IdeaItem.from_dict(data)

    async def evaluate_and_wait(self, description: str, files: list[str] | None = None, timeout: float = 120) -> IdeaItem:
        """提交评估任务并等待结果。"""
        task = await self.evaluate(description, files=files)
        return await self.get_result(task.task_id, timeout=timeout)


class DisclosureClient(_ModuleClient):
    """M2 交底书 Agent client."""

    def __init__(self, parent: IpClient):
        super().__init__(parent, "ip-disclosure")

    async def generate(
        self,
        idea_id: str | None = None,
        description: str | None = None,
        files: list[str] | None = None,
    ) -> TaskResponse:
        params: dict[str, Any] = {}
        if idea_id:
            params["ideaId"] = idea_id
        if description:
            params["description"] = description
        if files:
            params["files"] = files
        return await self._submit(params)

    async def get_result(self, task_id: str, timeout: float = 120) -> IpDisclosure:
        data = await self._poll("disclosure", task_id, timeout=timeout)
        return IpDisclosure.from_dict(data)

    async def update_section(self, disclosure_id: str, section_key: str, content: str) -> dict:
        return await self._parent._put(
            f"/api/ip/disclosure/{disclosure_id}/sections/{section_key}",
            json={"content": content},
        )

    async def export(self, disclosure_id: str) -> ExportInfo:
        data = await self._parent._get(f"/api/ip/disclosure/{disclosure_id}/export")
        return ExportInfo(**data["data"])

    async def generate_and_wait(
        self,
        idea_id: str | None = None,
        description: str | None = None,
        timeout: float = 120,
    ) -> IpDisclosure:
        task = await self.generate(idea_id=idea_id, description=description)
        return await self.get_result(task.task_id, timeout=timeout)


class DraftClient(_ModuleClient):
    """M3 智能撰写 Agent client."""

    def __init__(self, parent: IpClient):
        super().__init__(parent, "ip-draft")

    async def generate(
        self,
        disclosure_id: str,
        target_country: str = "CN",
        strategy: str = "broad",
    ) -> TaskResponse:
        return await self._submit({
            "disclosureId": disclosure_id,
            "targetCountry": target_country,
            "strategy": strategy,
        })

    async def get_result(self, task_id: str, timeout: float = 120) -> IpDraft:
        data = await self._poll("draft", task_id, timeout=timeout)
        return IpDraft.from_dict(data)

    async def export(self, draft_id: str, format: str = "docx") -> ExportInfo:
        data = await self._parent._get(f"/api/ip/draft/{draft_id}/export", params={"format": format})
        return ExportInfo(**data["data"])

    async def spawn_multi_country(self, draft_id: str, target_country: str) -> TaskResponse:
        data = await self._parent._post(f"/api/ip/draft/{draft_id}/spawn/{target_country}")
        return TaskResponse(task_id=data["data"]["taskId"])

    async def generate_and_wait(
        self,
        disclosure_id: str,
        target_country: str = "CN",
        strategy: str = "broad",
        timeout: float = 120,
    ) -> IpDraft:
        task = await self.generate(disclosure_id, target_country, strategy)
        return await self.get_result(task.task_id, timeout=timeout)


class FilingClient(_ModuleClient):
    """M4 全球申请管家 client."""

    def __init__(self, parent: IpClient):
        super().__init__(parent, "ip-filing")

    async def analyze(
        self,
        draft_id: str,
        target_markets: list[str],
        path: str | None = None,
    ) -> TaskResponse:
        params: dict[str, Any] = {"draftId": draft_id, "targetMarkets": target_markets}
        if path:
            params["path"] = path
        return await self._submit(params)

    async def get_result(self, task_id: str, timeout: float = 120) -> IpFiling:
        data = await self._poll("filing", task_id, timeout=timeout)
        return IpFiling.from_dict(data)

    async def analyze_and_wait(
        self,
        draft_id: str,
        target_markets: list[str],
        path: str | None = None,
        timeout: float = 120,
    ) -> IpFiling:
        task = await self.analyze(draft_id, target_markets, path=path)
        return await self.get_result(task.task_id, timeout=timeout)


class OaReplyClient(_ModuleClient):
    """M5 OA 答复 Agent client."""

    def __init__(self, parent: IpClient):
        super().__init__(parent, "ip-oa-reply")

    async def analyze(
        self,
        country: str,
        draft_id: str | None = None,
        oa_file_path: str | None = None,
        strategy: str | None = None,
    ) -> TaskResponse:
        """分析 OA 通知书。

        Args:
            country: 目标国 (CN/US/EP/JP/KR)
            draft_id: 关联的专利申请ID
            oa_file_path: OA 通知书本地文件路径
            strategy: 答复策略偏好
        """
        if oa_file_path:
            with open(oa_file_path, "rb") as f:
                files = {"file": f}
                form_data = {"draftId": draft_id or "", "country": country}
                if strategy:
                    form_data["strategy"] = strategy
                data = await self._parent._post_form(
                    f"/api/team/{self._slug}/run",
                    data=form_data,
                    files=files,
                )
                return TaskResponse(task_id=data["taskId"])
        else:
            return await self._submit({
                "draftId": draft_id,
                "country": country,
                "strategy": strategy,
            })

    async def get_result(self, task_id: str, timeout: float = 120) -> IpOaRecord:
        data = await self._poll("oa-reply", task_id, timeout=timeout)
        return IpOaRecord.from_dict(data)

    async def analyze_and_wait(
        self,
        country: str,
        draft_id: str | None = None,
        oa_file_path: str | None = None,
        timeout: float = 120,
    ) -> IpOaRecord:
        task = await self.analyze(country, draft_id, oa_file_path)
        return await self.get_result(task.task_id, timeout=timeout)


class ReverseDetectionClient(_ModuleClient):
    """M6 反向侵权探测 client."""

    def __init__(self, parent: IpClient):
        super().__init__(parent, "ip-reverse-detection")

    async def reverse_detection(
        self,
        my_tech_description: str,
        my_patent_numbers: list[str] | None = None,
        target_markets: list[str] | None = None,
    ) -> TaskResponse:
        params: dict[str, Any] = {
            "myTechDescription": my_tech_description,
        }
        if my_patent_numbers:
            params["myPatentNumbers"] = my_patent_numbers
        if target_markets:
            params["targetMarkets"] = target_markets
        return await self._submit(params)

    async def get_result(self, task_id: str, timeout: float = 120) -> dict[str, Any]:
        data = await self._poll("reverse-detection", task_id, timeout=timeout)
        return data

    async def export_evidence(self, detection_id: str, alert_id: str) -> ExportInfo:
        data = await self._parent._get(
            f"/api/ip/reverse-detection/{detection_id}/evidence/{alert_id}"
        )
        return ExportInfo(**data["data"])

    async def export_warning(self, detection_id: str, alert_id: str) -> ExportInfo:
        data = await self._parent._get(
            f"/api/ip/reverse-detection/{detection_id}/warning/{alert_id}"
        )
        return ExportInfo(**data["data"])

    async def reverse_detection_and_wait(
        self,
        my_tech_description: str,
        my_patent_numbers: list[str] | None = None,
        timeout: float = 120,
    ) -> dict[str, Any]:
        task = await self.reverse_detection(my_tech_description, my_patent_numbers=my_patent_numbers)
        return await self.get_result(task.task_id, timeout=timeout)


class PortfolioClient(_ModuleClient):
    """M7 资产仪表盘 client."""

    def __init__(self, parent: IpClient):
        super().__init__(parent, "ip-portfolio")

    async def analyze(self, params: dict[str, Any] | None = None) -> TaskResponse:
        return await self._submit(params or {})

    async def get_result(self, task_id: str, timeout: float = 120) -> IpPortfolio:
        data = await self._poll("portfolio", task_id, timeout=timeout)
        return IpPortfolio.from_dict(data)

    async def export(self, portfolio_id: str, format: str = "pdf") -> ExportInfo:
        data = await self._parent._get(
            f"/api/ip/portfolio/{portfolio_id}/export",
            params={"format": format},
        )
        return ExportInfo(**data["data"])

    async def analyze_and_wait(self, timeout: float = 120) -> IpPortfolio:
        task = await self.analyze()
        return await self.get_result(task.task_id, timeout=timeout)


class TrademarkClient(_ModuleClient):
    """M8 商标注册助手 client."""

    def __init__(self, parent: IpClient):
        super().__init__(parent, "ip-trademark")

    async def generate(
        self,
        name: str,
        description: str | None = None,
        image_file_id: str | None = None,
        business_scope: str | None = None,
    ) -> TaskResponse:
        params: dict[str, Any] = {"name": name}
        if description:
            params["description"] = description
        if image_file_id:
            params["imageFileId"] = image_file_id
        if business_scope:
            params["businessScope"] = business_scope
        return await self._submit(params)

    async def get_result(self, task_id: str, timeout: float = 120) -> IpTrademark:
        data = await self._poll("trademark", task_id, timeout=timeout)
        return IpTrademark.from_dict(data)

    async def export_goods_list(self, trademark_id: str) -> ExportInfo:
        data = await self._parent._get(f"/api/ip/trademark/{trademark_id}/goods-list")
        return ExportInfo(**data["data"])

    async def export_package(self, trademark_id: str) -> ExportInfo:
        data = await self._parent._get(f"/api/ip/trademark/{trademark_id}/package")
        return ExportInfo(**data["data"])

    async def export_material(self, trademark_id: str) -> ExportInfo:
        data = await self._parent._get(f"/api/ip/trademark/{trademark_id}/material")
        return ExportInfo(**data["data"])

    async def generate_and_wait(
        self,
        name: str,
        description: str | None = None,
        timeout: float = 120,
    ) -> IpTrademark:
        task = await self.generate(name, description=description)
        return await self.get_result(task.task_id, timeout=timeout)


class IpClient:
    """DavyBot IP Module REST API client.

    Provides per-module sub-clients (M1-M8).

    Usage:
        async with IpClient("https://api.normnomos.com") as client:
            task = await client.idea_vault.evaluate("an AI scheduling algorithm")
            result = await client.idea_vault.get_result(task.task_id)
            print(result.patentability_score)

        # Sync shortcut:
        client = IpClient("https://api.normnomos.com")
        result = client.sync(client.idea_vault.evaluate_and_wait("an AI scheduling algorithm"))
    """

    def __init__(self, base_url: str = "", token: str | None = None, timeout: float = 30):
        if not base_url:
            raise ValueError("IpClient requires an explicit base_url (E1: no cloud default)")
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(timeout),
        )

        # Per-module sub-clients
        self.idea_vault = IdeaVaultClient(self)
        self.disclosure = DisclosureClient(self)
        self.draft = DraftClient(self)
        self.filing = FilingClient(self)
        self.oa_reply = OaReplyClient(self)
        self.reverse_detection = ReverseDetectionClient(self)
        self.portfolio = PortfolioClient(self)
        self.trademark = TrademarkClient(self)

    # ─── HTTP helpers (internal) ───

    def _headers(self) -> dict[str, str]:
        h = {"Accept": "application/json"}
        if self._token:
            h["Authorization"] = f"Bearer {self._token}"
        return h

    async def _get(self, path: str, params: dict | None = None) -> dict:
        resp = await self._client.get(path, headers=self._headers(), params=params)
        resp.raise_for_status()
        return resp.json()

    async def _post(self, path: str, json: dict | None = None) -> dict:
        resp = await self._client.post(path, headers=self._headers(), json=json)
        resp.raise_for_status()
        return resp.json()

    async def _post_form(self, path: str, data: dict | None = None, files: dict | None = None) -> dict:
        headers = self._headers()
        # Let httpx set content-type for multipart
        headers.pop("Content-Type", None)
        resp = await self._client.post(path, headers=headers, data=data, files=files)
        resp.raise_for_status()
        return resp.json()

    async def _put(self, path: str, json: dict | None = None) -> dict:
        resp = await self._client.put(path, headers=self._headers(), json=json)
        resp.raise_for_status()
        return resp.json()

    async def _sleep(self, seconds: float) -> None:
        await self._client._transport._pool._backend._sleep(seconds)

    # ─── File upload ───

    async def upload_file(self, file_path: str) -> FileUploadResult:
        """上传文件并返回 fileId。

        Args:
            file_path: 本地文件路径
        """
        with open(file_path, "rb") as f:
            files = {"file": f}
            headers = self._headers()
            headers.pop("Content-Type", None)
            resp = await self._client.post(
                "/api/ip/upload",
                headers=headers,
                files=files,
            )
            resp.raise_for_status()
            data = resp.json()
            return FileUploadResult(**data["data"])

    # ─── Context manager ───

    async def __aenter__(self) -> IpClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()

    async def close(self) -> None:
        await self._client.aclose()

    # ─── Sync helpers ───

    @staticmethod
    def sync(coro):
        """Run a coroutine synchronously (for REPL/script use)."""
        import asyncio
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            import nest_asyncio
            nest_asyncio.apply()
            return loop.run_until_complete(coro)
        return asyncio.run(coro)
