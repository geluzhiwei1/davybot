# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""
IP 知识产权模块 API 路由

为 davybot-app 前端提供 8 大 IP 模块的后端 API 端点：
  M1 创意保护舱 → /api/team/ip-idea-vault/run
  M2 交底书 Agent → /api/team/ip-disclosure/run
  M3 智能撰写 Agent → /api/team/ip-draft/run
  M4 全球申请管家 → /api/team/ip-filing/run
  M5 OA 答复 Agent → /api/team/ip-oa-reply/run
  M6 反向侵权探测 → /api/team/ip-reverse-detection/run
  M7 资产仪表盘 → /api/team/ip-portfolio/run
  M8 商标注册助手 → /api/team/ip-trademark/run

架构模式：
  - POST /api/team/{team_slug}/run → 提交任务，返回 {taskId}
  - GET /api/ip/{module}/{taskId} → 轮询任务结果
  - 任务异步执行，前端通过 taskId 轮询获取结果
  - Agent 引擎已集成：有 workspace 时启动真实 Agent 执行，无 workspace 时使用 mock 降级
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, Form, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel, Field

from dawei.config.settings import get_settings
from dawei.core.datetime_compat import UTC
from dawei.api.ip_task_store import task_store
from dawei.api import ip_exports

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["ip"])

# ─── 常量 ───

_MAX_TASK_STORE_SIZE = 10000  # 内存中最多保留的任务数
_MAX_TASK_AGE_SECONDS = 3600  # 任务最大保留时间（1小时）

# ─── 持久化任务存储（JSON 文件 + 内存缓存，跨重启恢复）───
# task_store 是 PersistentTaskDict 单例，对调用方完全透明（dict 子类）。
# 启动时从磁盘加载历史任务。
task_store.load()


def _cleanup_old_tasks() -> None:
    """清理过期任务（委托给持久化存储）。"""
    task_store.cleanup_expired(max_age_seconds=_MAX_TASK_AGE_SECONDS)

# ─── Pydantic 模型 ───


class TaskResponse(BaseModel):
    """任务提交响应"""
    taskId: str
    workspaceId: str | None = None


class TeamRunRequest(BaseModel):
    """Team run 通用请求体（各模块参数不同，使用宽松模型）"""
    model_config = {"extra": "allow"}

    # M1
    description: str | None = None
    files: list[str] | None = None
    # M2
    ideaId: str | None = None
    # M3
    disclosureId: str | None = None
    targetCountry: str | None = None
    strategy: str | None = None
    # M4
    draftId: str | None = None
    targetMarkets: list[str] | None = None
    path: str | None = None
    # M5
    country: str | None = None
    # M6
    patentNumbers: list[str] | None = None
    targetPatentNumbers: list[str] | None = None
    productDescription: str | None = None
    # M8
    name: str | None = None
    imageFileId: str | None = None
    businessScope: str | None = None


class DisclosureSectionUpdate(BaseModel):
    """交底书章节更新"""
    content: str


# ─── 辅助函数 ───


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _generate_task_id() -> str:
    return str(uuid.uuid4())


def _team_slug_to_module(slug: str) -> str:
    """将 team slug 映射到 IP 模块路径前缀"""
    mapping = {
        "ip-idea-vault": "evaluate",
        "ip-disclosure": "disclosure",
        "ip-draft": "draft",
        "ip-filing": "filing",
        "ip-oa-reply": "oa-reply",
        "ip-reverse-detection": "reverse-detection",
        "ip-portfolio": "portfolio",
        "ip-trademark": "trademark",
    }
    return mapping.get(slug, slug)


def _create_mock_ip_idea(params: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "title": params.get("description", "未命名创意")[:60] if params.get("description") else "新创意评估",
        "description": params.get("description", ""),
        "patentabilityScore": 78,
        "noveltyAnalysis": {
            "score": 82,
            "closestPriorArts": [
                {"title": "US11223344B2 - 类似技术方案", "relevance": "72%", "keyDifferences": "本方案采用分布式架构，对比文件为中心化架构"},
                {"title": "CN20231000001A - 相关领域方法", "relevance": "65%", "keyDifferences": "本方案引入了实时反馈机制"},
            ],
            "summary": "技术方案具有明显的新颖性，核心创新点未被现有专利覆盖。建议进一步检索非专利文献。",
        },
        "inventiveness": {
            "score": 74,
            "technicalProblem": "解决了传统方法中效率低下和数据不一致的问题",
            "nonObviousness": "本领域技术人员在面对该问题时，不会自然想到采用本方案的组合技术手段",
            "summary": "具备创造性，建议提供实验数据或对比数据以增强说服力。",
        },
        "industrialApplicability": {"score": 88, "applicableIndustries": ["信息技术", "智能制造", "金融科技"], "summary": "具有广泛的工业应用前景。"},
        "protectionSuggestions": [
            {"type": "发明专利", "priority": "high", "rationale": "核心技术方案适用于发明专利保护"},
            {"type": "PCT申请", "priority": "medium", "rationale": "建议考虑国际保护，目标市场包括美、欧、日"},
        ],
        "recommendedStrategy": "建议尽快提交发明专利申请，同时准备PCT申请。技术方案具有较好的可专利性基础。",
        "status": "completed",
        "createdAt": _now_iso(),
    }


def _create_mock_disclosure(params: dict[str, Any]) -> dict[str, Any]:
    title = params.get("description", "技术交底书")[:40] if params.get("description") else "技术交底书"
    return {
        "id": params.get("disclosureId") or str(uuid.uuid4()),
        "title": title,
        "status": "completed",
        "sections": {
            "technicalField": {
                "title": "技术领域",
                "content": "本发明涉及信息技术领域，具体涉及一种基于分布式架构的智能数据处理方法及系统。",
            },
            "backgroundArt": {
                "title": "背景技术",
                "content": "现有技术中，数据处理通常采用集中式架构，存在单点故障、处理效率低等问题。现有方案如专利US11223344B2提出了一种改进方法，但仍存在数据一致性方面的不足。",
            },
            "technicalProblem": {
                "title": "要解决的技术问题",
                "content": "本发明要解决的技术问题是：如何在不降低处理效率的前提下，保证分布式数据处理系统的一致性和可靠性。",
            },
            "technicalSolution": {
                "title": "技术方案",
                "content": "本发明提供一种分布式智能数据处理方法，包括：步骤1，接收数据处理请求；步骤2，将请求分解为多个子任务；步骤3，通过优化调度算法将子任务分配至各处理节点；步骤4，各节点并行处理并在完成后同步结果。",
            },
            "beneficialEffects": {
                "title": "有益效果",
                "content": "1. 处理效率提升40%以上；2. 数据一致性保障率达99.99%；3. 系统可用性显著提高；4. 运维成本降低30%。",
            },
            "embodiments": {
                "title": "具体实施方式",
                "content": "实施例1：数据处理系统包括请求接收模块、任务分解模块、调度模块、执行模块和结果聚合模块…",
            },
            "drawings": {
                "title": "附图说明",
                "content": "图1 系统架构图\n图2 数据流程图\n图3 调度算法流程图",
            },
            "claims": {
                "title": "权利要求概要",
                "content": "1. 一种分布式智能数据处理方法，其特征在于，包括如下步骤…\n2. 如权利要求1所述的方法，其中所述优化调度算法基于机器学习的预测模型…",
            },
        },
        "createdAt": _now_iso(),
    }


def _create_mock_draft(params: dict[str, Any]) -> dict[str, Any]:
    country = params.get("targetCountry", "CN")
    country_label = {"CN": "中国", "US": "美国", "EP": "欧洲", "JP": "日本", "KR": "韩国"}.get(country, country)
    return {
        "id": str(uuid.uuid4()),
        "title": f"一种分布式智能数据处理方法及系统 - {country_label}申请",
        "targetCountry": country,
        "status": "completed",
        "strategy": params.get("strategy", "broad"),
        "claims": [
            {"id": "claim-1", "number": 1, "type": "independent", "content": "一种分布式智能数据处理方法，其特征在于，包括如下步骤：接收数据处理请求；将所述请求分解为多个子任务；通过优化调度算法将所述子任务分配至各处理节点；各节点并行处理所述子任务，并在完成后同步处理结果。"},
            {"id": "claim-2", "number": 2, "type": "dependent", "content": "如权利要求1所述的方法，其中所述优化调度算法基于机器学习的预测模型，用于预测各节点的处理能力和当前负载。"},
            {"id": "claim-3", "number": 3, "type": "dependent", "content": "如权利要求1所述的方法，其中所述结果同步采用分布式一致性协议。"},
            {"id": "claim-4", "number": 4, "type": "dependent", "content": "如权利要求1所述的方法，还包括：在所述子任务分配前，对所述数据处理请求进行预处理和格式标准化。"},
            {"id": "claim-5", "number": 5, "type": "dependent", "content": "如权利要求1所述的方法，其中所述各节点并行处理包括：使用容器化技术进行隔离执行。"},
            {"id": "claim-6", "number": 6, "type": "independent", "content": "一种分布式智能数据处理系统，其特征在于，包括：请求接收模块、任务分解模块、调度模块、多个处理节点和结果聚合模块。"},
            {"id": "claim-7", "number": 7, "type": "dependent", "content": "如权利要求6所述的系统，其中所述调度模块包括机器学习预测单元。"},
        ],
        "specification": {
            "technicalField": "本发明涉及信息技术领域，具体涉及一种基于分布式架构的智能数据处理方法及系统。",
            "backgroundArt": "随着大数据时代的到来，传统集中式数据处理架构已难以满足日益增长的处理需求…",
            "summary": "本发明提供一种分布式智能数据处理方法及系统，通过优化调度算法提高处理效率，同时保证数据一致性。",
            "detailedDescription": "下面结合附图和具体实施例对本发明做进一步详细说明…",
            "examples": "实施例1\n参考图1，本实施例的数据处理系统包括…",
        },
        "complianceCheck": {
            "overallStatus": "pass",
            "issues": [
                {"type": "warning", "message": "权利要求6的'结果聚合模块'建议与权利要求1保持术语一致", "severity": "low"},
            ],
        },
        "createdAt": _now_iso(),
    }


def _create_mock_filing(params: dict[str, Any]) -> dict[str, Any]:
    markets = params.get("targetMarkets", ["US", "EP"])
    return {
        "id": str(uuid.uuid4()),
        "draftId": params.get("draftId", ""),
        "status": "completed",
        "targetMarkets": markets,
        "recommendedPath": "PCT",
        "pathComparison": {
            "parisPath": {"deadline": "12个月", "fees": {}, "pros": ["单一国费用低", "直接审查开始早"], "cons": ["需同时提交多国译文", "各国独立审查"]},
            "pctPath": {"deadline": "30个月（优先权日起）", "fees": {"internationalPhase": "CHF 1330+", "nationalPhasePerCountry": "视各国而定"}, "pros": ["延长决策时间至30个月", "国际检索报告辅助判断", "统一形式审查"], "cons": ["国际阶段额外费用", "各国审查推迟"]},
            "recommendation": "建议采用PCT路径",
        },
        "priorities": [{"id": "pri-1", "country": "CN", "filingDate": "2025-01-15", "applicationNumber": "CN20251000001.0", "deadline": "2026-01-15"}],
        "fees": [
            {"country": "CN", "officialFee": 3450, "agentFee": 8000, "total": 11450},
            {"country": "US", "officialFee": 3200, "agentFee": 35000, "total": 38200, "note": "含美国代理费"},
            {"country": "EP", "officialFee": 4530, "agentFee": 28000, "total": 32530},
        ]
        + (
            [{"country": "JP", "officialFee": 2800, "agentFee": 25000, "total": 27800}]
            if "JP" in markets
            else []
        )
        + (
            [{"country": "KR", "officialFee": 2100, "agentFee": 18000, "total": 20100}]
            if "KR" in markets
            else []
        ),
        "pctTimeline": [
            {"stage": "RO", "name": "受理局提交", "deadline": "2025-07-15", "status": "completed", "description": "向CNIPA-RO提交PCT申请"},
            {"stage": "ISA", "name": "国际检索", "deadline": "2026-01-15", "status": "in_progress", "description": "国际检索单位出具检索报告"},
            {"stage": "IB", "name": "国际公布", "deadline": "2026-07-15", "status": "pending", "description": "WIPO国际公布"},
            {"stage": "SIS", "name": "补充国际检索(可选)", "deadline": "2026-10-15", "status": "pending", "description": "请求补充国际检索"},
            {"stage": "IPEA", "name": "国际初步审查(可选)", "deadline": "2026-10-15", "status": "pending", "description": "请求国际初步审查"},
            {"stage": "NP", "name": "进入国家阶段", "deadline": "2027-07-15", "status": "pending", "description": "30个月前进入各国国家阶段"},
        ],
        "translations": [
            {"sourceLang": "zh", "targetLang": "en", "targetCountry": "US", "status": "in_progress", "filename": "us-translation-en-v1.docx"},
            {"sourceLang": "zh", "targetLang": "en", "targetCountry": "EP", "status": "pending", "filename": ""},
            {"sourceLang": "zh", "targetLang": "ja", "targetCountry": "JP", "status": "pending", "filename": ""},
        ],
        "createdAt": _now_iso(),
    }


def _create_mock_oa_reply(params: dict[str, Any]) -> dict[str, Any]:
    country = params.get("country", "CN")
    return {
        "id": str(uuid.uuid4()),
        "draftId": params.get("draftId", ""),
        "status": "completed",
        "country": country,
        "oaNumber": f"OA-{datetime.now().strftime('%Y%m%d')}-001",
        "oaDate": _now_iso(),
        "deadline": "2026-01-15",
        "rejections": [
            {"type": "novelty", "legalBasis": "专利法第22条第2款", "description": "权利要求1-2相对于对比文件D1(US11223344B2)不具备新颖性。", "strength": "medium"},
            {"type": "inventiveStep", "legalBasis": "专利法第22条第3款", "description": "权利要求3-5的技术特征在D1的基础上结合D2(CN20231000001A)是显而易见的。", "strength": "weak"},
        ],
        "comparedDocuments": [
            {"id": "D1", "title": "US11223344B2", "relevance": "72%", "comparison": "D1公开了数据处理的基本方法，但未涉及本发明的优化调度算法和实时反馈机制。"},
            {"id": "D2", "title": "CN20231000001A", "relevance": "65%", "comparison": "D2涉及数据处理系统中的负载均衡，但采用的是静态分配方法，不同于本发明的基于机器学习的动态调度。"},
        ],
        "recommendedStrategy": "争辩+修改",
        "strategyAnalysis": {
            "arguable": [
                "D1未公开'基于机器学习的预测模型'的特征",
                "D2的静态分配不同于本发明的'优化调度算法'",
                "权利要求6的系统结构具有独特的模块组合",
            ],
            "claimAmendments": [
                "在权利要求1中进一步限定'所述优化调度算法基于机器学习的预测模型'",
                "在权利要求6中加入'所述调度模块包括GPU加速单元'",
            ],
        },
        "replies": [
            {"type": "argument", "legalBasis": "专利法第22条第2款", "content": "针对新颖性驳回，申请人认为D1并未公开本发明的'基于机器学习的预测模型'特征…", "strength": "strong"},
            {"type": "amendment", "legalBasis": "专利法第22条第3款", "content": "将原权利要求1中的'优化调度算法'进一步限定为'基于机器学习的预测模型的优化调度算法'…", "strength": "strong"},
        ],
        "amendedClaims": [
            {"number": 1, "type": "independent", "content": "一种分布式智能数据处理方法，其特征在于，包括如下步骤：[新增]通过基于机器学习的预测模型的优化调度算法…", "changes": "added limitation"},
            {"number": 2, "type": "dependent", "content": "如权利要求1所述的方法，其中所述机器学习预测模型包括训练阶段和推理阶段。", "changes": "amended"},
        ],
        "createdAt": _now_iso(),
    }


def _create_mock_reverse_detection(params: dict[str, Any]) -> dict[str, Any]:
    """生成反向侵权探测 mock 数据 — 检测他人侵犯我方专利"""
    my_patents = params.get("myPatentNumbers", [])
    my_tech = params.get("myTechDescription", "")
    sample_patent = my_patents[0] if my_patents else "CN20231000001.X"
    return {
        "id": str(uuid.uuid4()),
        "type": params.get("type", "reverse_patent"),
        "myPatentNumbers": my_patents,
        "myTechDescription": my_tech,
        "targetMarkets": params.get("targetMarkets", ["CN", "US"]),
        "status": "completed",
        "results": [
            {
                "id": "res-001",
                "infringerName": "某科技有限公司",
                "infringerProduct": "智能数据处理平台 v3.0",
                "matchedMyPatentNumber": sample_patent,
                "infringementProbability": "high",
                "featureMatchRate": 85,
                "claimMatches": [
                    {
                        "myClaimNumber": 1,
                        "myClaimText": "一种分布式智能数据处理方法，其特征在于，包括基于机器学习预测模型的资源调度步骤",
                        "theirFeature": "产品采用AI驱动的资源调度引擎进行任务分配",
                        "matchLevel": "exact",
                        "analysis": "侵权产品完全覆盖了权利要求1的技术特征，特别是机器学习预测模型调度部分",
                    },
                    {
                        "myClaimNumber": 2,
                        "myClaimText": "如权利要求1所述的方法，其中所述机器学习预测模型包括训练阶段和推理阶段",
                        "theirFeature": "产品文档描述两阶段AI模型：离线训练和在线推理",
                        "matchLevel": "exact",
                        "analysis": "技术实现路径一致，均采用训练-推理两阶段架构",
                    },
                ],
                "alert": {
                    "id": "alert-001",
                    "type": "patent",
                    "title": f"高侵权概率：侵权方-某科技有限公司",
                    "description": f"该公司的产品高度疑似侵犯我方专利 {sample_patent}，特征匹配率 85%，建议立即取证并发出警告函。",
                    "severity": "high",
                    "createdAt": _now_iso(),
                    "read": False,
                },
            },
            {
                "id": "res-002",
                "infringerName": "某数据集团",
                "infringerProduct": "分布式计算引擎 v2.1",
                "matchedMyPatentNumber": sample_patent,
                "infringementProbability": "medium",
                "featureMatchRate": 62,
                "claimMatches": [
                    {
                        "myClaimNumber": 1,
                        "myClaimText": "一种分布式智能数据处理方法，其特征在于，包括基于机器学习预测模型的资源调度步骤",
                        "theirFeature": "引擎使用规则引擎而非机器学习的资源调度策略",
                        "matchLevel": "partial",
                        "analysis": "产品采用传统规则引擎，未采用机器学习预测模型，仅部分匹配",
                    },
                ],
                "alert": {
                    "id": "alert-002",
                    "type": "patent",
                    "title": "中等侵权概率：某数据集团",
                    "description": "该公司的产品部分匹配我方专利特征，但核心创新点未被覆盖，建议持续关注。",
                    "severity": "medium",
                    "createdAt": _now_iso(),
                    "read": False,
                },
            },
        ],
        "createdAt": _now_iso(),
        "updatedAt": _now_iso(),
    }


def _create_mock_portfolio(params: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "status": "completed",
        "patents": [
            {"id": "pat-1", "title": "分布式数据处理方法及系统", "patentNumber": "CN20231000001.0", "status": "granted", "priorityDate": "2023-01-15", "filingDate": "2023-01-15", "grantDate": "2024-06-20", "expiryDate": "2043-01-15", "inventors": ["张三", "李四"], "patentType": "invention", "valueScore": 82, "technicalValue": 85, "legalValue": 78, "economicValue": 83, "familySize": 5, "productRelation": "core", "citationCount": 12},
            {"id": "pat-2", "title": "基于AI的任务调度系统", "patentNumber": "CN20232000002.1", "status": "pending", "priorityDate": "2023-06-10", "filingDate": "2023-06-10", "inventors": ["王五"], "patentType": "invention", "valueScore": 68, "technicalValue": 72, "legalValue": 65, "economicValue": 67, "familySize": 3, "productRelation": "supporting", "citationCount": 5},
            {"id": "pat-3", "title": "数据一致性验证装置", "patentNumber": "CN20241000003.3", "status": "granted", "priorityDate": "2024-02-20", "filingDate": "2024-02-20", "grantDate": "2025-03-15", "expiryDate": "2044-02-20", "inventors": ["张三"], "patentType": "utilityModel", "valueScore": 65, "technicalValue": 62, "legalValue": 70, "economicValue": 63, "familySize": 1, "productRelation": "auxiliary", "citationCount": 3},
            {"id": "pat-4", "title": "实时流数据处理方法", "patentNumber": "CN20241000004.5", "status": "pending", "priorityDate": "2024-08-05", "filingDate": "2024-08-05", "inventors": ["李四", "赵六"], "patentType": "invention", "valueScore": 74, "technicalValue": 78, "legalValue": 70, "economicValue": 74, "familySize": 2, "productRelation": "core", "citationCount": 1},
            {"id": "pat-5", "title": "智能数据预处理接口", "patentNumber": "CN20242000005.2", "status": "abandoned", "priorityDate": "2024-03-15", "filingDate": "2024-03-15", "inventors": ["王五"], "patentType": "invention", "valueScore": 42, "technicalValue": 45, "legalValue": 40, "economicValue": 41, "familySize": 1, "productRelation": "none", "citationCount": 0},
            {"id": "pat-6", "title": "分布式计算资源管理方法", "patentNumber": "CN20241000008.7", "status": "pending", "priorityDate": "2024-11-01", "filingDate": "2024-11-01", "inventors": ["赵六"], "patentType": "invention", "valueScore": 60, "technicalValue": 65, "legalValue": 55, "economicValue": 60, "familySize": 1, "productRelation": "supporting", "citationCount": 0},
            {"id": "pat-7", "title": "故障自动检测与恢复系统", "patentNumber": "PCT/CN2024/000001", "status": "pending", "priorityDate": "2024-06-01", "filingDate": "2024-06-01", "inventors": ["张三", "王五"], "patentType": "invention", "valueScore": 55, "technicalValue": 58, "legalValue": 52, "economicValue": 55, "familySize": 8, "productRelation": "auxiliary", "citationCount": 2},
            {"id": "pat-8", "title": "机器学习模型部署框架", "patentNumber": "CN20241000009.0", "status": "granted", "priorityDate": "2023-09-12", "filingDate": "2023-09-12", "grantDate": "2025-01-20", "expiryDate": "2043-09-12", "inventors": ["李四"], "patentType": "invention", "valueScore": 88, "technicalValue": 90, "legalValue": 85, "economicValue": 89, "familySize": 6, "productRelation": "core", "citationCount": 18},
        ],
        "trademarks": [
            {"id": "tm-1", "name": "DataMatrix", "registrationNumber": "TM20230001", "status": "registered", "classes": [9, 42], "filingDate": "2023-05-01", "registrationDate": "2024-02-15", "expiryDate": "2034-02-14"},
            {"id": "tm-2", "name": "SmartFlow", "registrationNumber": "TM20240002", "status": "pending", "classes": [9, 35, 42], "filingDate": "2024-08-10"},
        ],
        "kpis": {
            "patent": {"total": 8, "granted": 3, "pending": 4, "abandoned": 1, "expired": 0, "thisYear": 3, "grantRate": 75.0, "avgClaims": 14.5, "avgCitationsPerPatent": 5.1},
            "trademark": {"total": 2, "registered": 1, "pending": 1, "opposed": 0, "thisYear": 1},
            "weightedAvgValueScore": 69.5,
        },
        "healthScore": 72,
        "healthSubScores": {"quality": 75, "coverage": 68, "lifespan": 65, "business": 80},
        "patentStatusDistribution": [{"status": "granted", "count": 3, "percentage": 37.5}, {"status": "pending", "count": 4, "percentage": 50.0}, {"status": "abandoned", "count": 1, "percentage": 12.5}, {"status": "expired", "count": 0, "percentage": 0}],
        "competitors": [
            {"id": "comp-1", "name": "TechNova Inc.", "patentCount": 45, "trademarkCount": 6, "patentQuality": 72, "topTechFields": ["数据处理", "AI/ML", "云计算"], "gapAnalysis": {"totalGap": 37, "qualityGap": 3, "coverageGap": 42}},
            {"id": "comp-2", "name": "DataSphere Corp.", "patentCount": 28, "trademarkCount": 4, "patentQuality": 65, "topTechFields": ["数据分析", "数据存储", "数据安全"], "gapAnalysis": {"totalGap": 20, "qualityGap": 10, "coverageGap": 28}},
            {"id": "comp-3", "name": "InnovaTech Solutions", "patentCount": 62, "trademarkCount": 12, "patentQuality": 78, "topTechFields": ["AI/ML", "数据处理", "自动化"], "gapAnalysis": {"totalGap": 54, "qualityGap": -6, "coverageGap": 60}},
        ],
        "renewals": {
            "next12Months": [
                {"patentId": "pat-3", "title": "数据一致性验证装置", "dueDate": "2025-08-20", "fee": 1800, "year": 3, "recommendedAction": "renew"},
                {"patentId": "pat-1", "title": "分布式数据处理方法及系统", "dueDate": "2025-12-15", "fee": 2400, "year": 4, "recommendedAction": "renew"},
                {"tm-1": {"trademarkId": "tm-1", "name": "DataMatrix", "dueDate": "2025-10-01", "fee": 450, "recommendedAction": "renew"}},
            ],
            "totalEstimatedFees": 4650,
        },
        "createdAt": _now_iso(),
    }


def _create_mock_trademark(params: dict[str, Any]) -> dict[str, Any]:
    tm_name = params.get("name", "商标名称")
    return {
        "id": str(uuid.uuid4()),
        "name": tm_name,
        "status": "completed",
        "recommendedClasses": [
            {"classNumber": 9, "className": "科学仪器、计算机软件", "type": "core", "goods": ["0901 已录制的计算机程序", "0901 可下载的计算机应用软件", "0901 数据处理设备", "0907 通信设备"], "rationale": "核心经营范围——软件产品"},
            {"classNumber": 42, "className": "科学技术服务、软件开发", "type": "core", "goods": ["4220 计算机软件设计", "4220 计算机软件更新", "4220 计算机软件维护", "4220 软件即服务(SaaS)"], "rationale": "核心经营范围——软件开发服务"},
            {"classNumber": 35, "className": "广告、商业管理", "type": "related", "goods": ["3501 广告", "3502 商业管理辅助", "3503 市场营销", "3506 计算机数据库信息处理"], "rationale": "关联经营范围——广告营销"},
            {"classNumber": 38, "className": "通讯服务", "type": "related", "goods": ["3802 信息传送", "3802 计算机辅助信息传送", "3802 数据流传输"], "rationale": "关联经营范围——数据传输"},
            {"classNumber": 41, "className": "教育、培训服务", "type": "defensive", "goods": ["4101 培训", "4101 教育信息", "4104 电子书籍和杂志在线出版"], "rationale": "防御性注册——防止他人在培训教育领域抢注"},
        ],
        "registrability": {
            "overallScore": 72,
            "overallRating": "medium",
            "distinctiveness": {"score": 68, "rating": "medium", "analysis": f"'{tm_name}'具有较强的暗示性，但经过使用可以获得显著性。不属于通用名称或纯描述性词汇。", "risk": "medium"},
            "absoluteGrounds": {"pass": True, "issues": []},
            "relativeGrounds": {"pass": True, "issues": [{"description": "在第9类中发现类似发音商标存在", "similarityScore": 45, "riskLevel": "low"}]},
            "similarTrademarks": [
                {"name": "类似商标A", "class": 9, "similarity": 45, "risk": "low"},
                {"name": "类似商标B", "class": 42, "similarity": 32, "risk": "low"},
            ],
            "summary": "商标整体可注册性评估为中，显著性方面需要提供使用证据支持，相对理由方面暂无重大障碍。建议增加商标设计元素以增强显著性。",
        },
        "createdAt": _now_iso(),
    }


# ─── 模块 Mock 数据工厂 ───

_MOCK_FACTORIES = {
    "ip-idea-vault": _create_mock_ip_idea,
    "ip-disclosure": _create_mock_disclosure,
    "ip-draft": _create_mock_draft,
    "ip-application": _create_mock_draft,  # fallback to draft mock; real: template-driven
    "ip-filing": _create_mock_filing,
    "ip-oa-reply": _create_mock_oa_reply,
    "ip-reverse-detection": _create_mock_reverse_detection,
    "ip-portfolio": _create_mock_portfolio,
    "ip-trademark": _create_mock_trademark,
}

# ─── Task 存储辅助 ───


def _store_task_initial(
    module_slug: str,
    task_id: str,
    params: dict[str, Any],
    workspace_id: str | None = None,
) -> None:
    """初始化任务条目为 running 状态（实际执行由后台 Agent 完成）。"""
    task_store[task_id] = {
        "module": module_slug,
        "status": "running",
        "result": None,
        "error": None,
        "createdAt": _now_iso(),
        "workspaceId": workspace_id,
        "phase": "starting",
    }
    _cleanup_old_tasks()


async def _launch_agent_background(
    module_slug: str,
    task_id: str,
    params: dict[str, Any],
    workspace_id: str | None = None,
) -> None:
    """Launch Agent execution as an asyncio background task.

    If workspace_id is available, the Agent runs inside that workspace;
    otherwise falls back to mock data immediately.
    """
    if workspace_id:
        from dawei.workspace.ip_agent_executor import execute_ip_task_background

        asyncio.create_task(
            execute_ip_task_background(
                task_store=task_store,
                task_id=task_id,
                workspace_id=workspace_id,
                module_slug=module_slug,
                params=params,
            )
        )
        logger.info(
            f"[IP Routes] Agent background task launched: "
            f"module={module_slug} taskId={task_id} ws={workspace_id}"
        )
    else:
        # Fallback: no workspace means no Agent execution possible
        factory = _MOCK_FACTORIES.get(module_slug)
        if factory:
            task_store[task_id] = {
                "module": module_slug,
                "status": "completed",
                "result": factory(params),
                "createdAt": _now_iso(),
                "workspaceId": None,
            }
        else:
            task_store[task_id] = {
                "module": module_slug,
                "status": "failed",
                "error": f"Unknown module: {module_slug}",
                "createdAt": _now_iso(),
                "workspaceId": None,
            }
        _cleanup_old_tasks()


# ─── 路由 ───

# ============================================================
# POST /api/team/{team_slug}/run — 统一 Agent 任务提交入口
# ============================================================

_VALID_TEAM_SLUGS = set(_MOCK_FACTORIES.keys())


def _bearer_token(http_request: Request) -> str | None:
    """Extract the Bearer JWT from the incoming request, if present.

    Delegate to the unified ``dawei.api.auth.extract_market_token``.
    """
    from dawei.api.auth import extract_market_token
    return extract_market_token(http_request)


@router.post("/team/{team_slug}/run", response_model=TaskResponse)
async def run_team(
    team_slug: str, http_request: Request, body: dict[str, Any] | None = None
):
    """提交 IP Agent 任务

    统一的 8 模块 Agent 任务提交入口。接收前端传递的参数（技术描述、文件等），
    创建异步任务并返回 taskId。前端通过 GET /api/ip/{module}/{taskId} 轮询任务结果。

    Phase 1 兼容模式: 自动为每个任务创建临时工作区，返回 workspaceId。
    工作区为任务提供多轮对话持久化、文件隔离和断点续做能力。

    Args:
        team_slug: Team 标识（如 ip-idea-vault, ip-disclosure, ...）
        body: 任务参数（各模块参数不同）

    Returns:
        { taskId: string, workspaceId?: string } — 用于后续轮询
    """
    if team_slug not in _VALID_TEAM_SLUGS:
        raise HTTPException(status_code=404, detail=f"Unknown team: {team_slug}")

    task_id = _generate_task_id()
    params = body or {}

    # Phase 1: 自动创建临时工作区 (非阻塞，失败不影响任务创建)
    workspace_id: str | None = None
    try:
        from dawei.models.ip import IpTaskContext
        from dawei.workspace.ip_workspace_service import ip_workspace_service

        task_type = params.get("task_type", params.get("type", "run"))
        description = params.get("description") or params.get("query") or params.get("idea")
        parent_workspace_id = params.get("parent_workspace_id") or params.get("workspaceId")

        context = IpTaskContext(
            module=team_slug,
            task_type=task_type,
            description=str(description) if description else None,
            parent_workspace_id=parent_workspace_id,
            language=params.get("language", "zh-CN"),
            jurisdiction=params.get("jurisdiction", "CN"),
            draft_strategy=params.get("strategy"),
            target_country=params.get("targetCountry"),
            file_ids=params.get("files") or [],
        )

        ws_status = await ip_workspace_service.create_ip_workspace(
            module=team_slug,
            task_context=context,
            market_token=_bearer_token(http_request),
        )
        workspace_id = ws_status.workspace_id
        logger.info(f"[IP Routes] Workspace created for task: ws={workspace_id} task={task_id}")
    except Exception as ws_err:
        logger.warning(f"[IP Routes] Failed to create workspace for {team_slug}: {ws_err}")

    _store_task_initial(team_slug, task_id, params, workspace_id)
    await _launch_agent_background(team_slug, task_id, params, workspace_id)

    logger.info(f"[IP Routes] Task created: team={team_slug} taskId={task_id} wsId={workspace_id}")
    return TaskResponse(taskId=task_id, workspaceId=workspace_id)


# ============================================================
# GET /api/ip/{module}/{taskId} — 任务结果轮询
# ============================================================


@router.get("/ip/{module}/{task_id}")
async def get_task_result(module: str, task_id: str):
    """获取 IP 任务执行结果

    轮询端点。返回当前任务状态。如果任务仍在运行中，返回 status 和 phase。
    如果任务已完成，返回结构化结果数据。
    也尝试从 workspace 的 .dawei/results.json 读取持久化结果作为回退。

    Args:
        module: 模块名（evaluate, disclosure, draft, filing, oa-reply, reverse-detection, portfolio, trademark）
        task_id: 任务ID（由 POST /api/team/{slug}/run 返回）

    Returns:
        任务结果对象，包含 status、data 和 workspaceId
    """
    task = task_store.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")

    if task["status"] == "failed":
        raise HTTPException(status_code=500, detail=task.get("error", "Task failed"))

    # 运行中：返回状态和阶段信息（前端据此显示进度）
    if task["status"] == "running":
        # 尝试从 workspace 读取已持久化的中间结果作为补充信息
        ws_id = task.get("workspaceId")
        workspace_result = None
        if ws_id:
            try:
                from dawei.workspace.ip_agent_executor import read_task_result_from_workspace

                workspace_result = await read_task_result_from_workspace(ws_id)
            except Exception:
                pass

        return {
            "success": True,
            "data": task.get("result") or workspace_result,
            "status": "running",
            "phase": task.get("phase", "unknown"),
            "workspaceId": task.get("workspaceId"),
            "conversationId": task.get("conversationId"),
            "messagesCount": task.get("messagesCount", 0),
            "toolCallsCount": task.get("toolCallsCount", 0),
        }

    return {"success": True, "data": task["result"], "workspaceId": task.get("workspaceId")}


# ============================================================
# M2 交底书 — 章节更新 + 导出
# ============================================================


@router.put("/ip/disclosure/{disclosure_id}/sections/{section_key}")
async def update_disclosure_section(disclosure_id: str, section_key: str, body: DisclosureSectionUpdate):
    """更新交底书指定章节内容"""
    return {"success": True, "message": f"Section {section_key} updated for disclosure {disclosure_id}"}


async def _get_ip_result(entity_id: str) -> dict[str, Any] | None:
    """从 task_store 或 workspace 恢复 IP 任务结果数据。

    entity_id 可能是 task_id，也可能是 workspace_id。
    """
    # 1. 直接作为 task_id 查找
    task = task_store.get(entity_id)
    if task:
        if task.get("result"):
            return task["result"]
        ws_id = task.get("workspaceId")
        if ws_id:
            try:
                from dawei.workspace.ip_agent_executor import read_task_result_from_workspace

                result = await read_task_result_from_workspace(ws_id)
                if result:
                    return result
            except Exception:
                pass
    # 2. 尝试作为 workspace_id 读 results.json
    try:
        from dawei.workspace.ip_agent_executor import read_task_result_from_workspace

        result = await read_task_result_from_workspace(entity_id)
        if result:
            return result
    except Exception:
        pass
    # 3. 遍历 task_store 找匹配 workspaceId 的结果
    for t in task_store.values():
        if isinstance(t, dict) and t.get("workspaceId") == entity_id and t.get("result"):
            return t["result"]
    return None


def _file_response(content: bytes, filename: str, media_type: str) -> Response:
    """构造文件下载响应。"""
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/ip/disclosure/{disclosure_id}/export")
async def export_disclosure_docx(disclosure_id: str):
    """导出交底书为 DOCX 文档"""
    result = await _get_ip_result(disclosure_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"交底书结果不存在: {disclosure_id}")
    content = ip_exports.generate_disclosure_docx(result)
    return _file_response(
        content, f"disclosure-{disclosure_id}.docx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


# ============================================================
# M3 智能撰写 — 导出 + 多国一键生成
# ============================================================


@router.get("/ip/draft/{draft_id}/export")
async def export_draft(draft_id: str, format: str = "docx"):
    """导出专利申请文件（DOCX 或 PDF）"""
    result = await _get_ip_result(draft_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"撰写结果不存在: {draft_id}")
    if format == "pdf":
        content = ip_exports.generate_draft_pdf(result)
        return _file_response(content, f"patent-draft-{draft_id}.pdf", "application/pdf")
    # 默认 docx
    content = ip_exports.generate_draft_docx(result)
    return _file_response(
        content, f"patent-draft-{draft_id}.docx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


@router.post("/ip/draft/{draft_id}/spawn/{target_country}")
async def spawn_multi_country_draft(draft_id: str, target_country: str):
    """为现有申请草稿生成目标国家/地区版本的申请文件"""
    country_names = {"US": "美国", "EP": "欧洲", "JP": "日本", "KR": "韩国", "CN": "中国"}
    if target_country not in country_names:
        raise HTTPException(status_code=400, detail=f"Unsupported target country: {target_country}")

    task_id = _generate_task_id()
    params = {"disclosureId": draft_id, "targetCountry": target_country}
    _store_task_initial("ip-draft", task_id, params)
    await _launch_agent_background("ip-draft", task_id, params)

    logger.info(f"[IP Routes] Multi-country draft spawned: {target_country} taskId={task_id}")
    return {"success": True, "data": {"taskId": task_id}}


# ============================================================
# M6 反向侵权探测 — 证据包 + 警告函导出
# ============================================================


@router.get("/ip/reverse-detection/{detection_id}/evidence/{alert_id}")
async def export_reverse_detection_evidence(detection_id: str, alert_id: str):
    """导出反向侵权探测证据包（ZIP：比对报告 + 警告函 + 结构化数据）"""
    result = await _get_ip_result(detection_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"探测结果不存在: {detection_id}")
    content = ip_exports.generate_evidence_zip(result, alert_id)
    return _file_response(content, f"evidence-{alert_id}.zip", "application/zip")


@router.get("/ip/reverse-detection/{detection_id}/warning/{alert_id}")
async def export_warning_letter(detection_id: str, alert_id: str):
    """导出反向侵权探测警告函（DOCX）"""
    result = await _get_ip_result(detection_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"探测结果不存在: {detection_id}")
    content = ip_exports.generate_warning_letter_docx(result, alert_id)
    return _file_response(
        content, f"warning-letter-{alert_id}.docx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


# ============================================================
# M7 资产仪表盘 — 实时聚合统计
# ============================================================


@router.get("/ip/portfolio/stats")
async def get_portfolio_stats():
    """聚合所有 IP 工作区数据，返回仪表盘 KPI 统计。

    响应:
        PortfolioStats { total_workspaces, health_score,
            patents_granted, patents_pending,
            trademarks_registered, trademarks_pending,
            new_this_year, modules, recent_workspaces }
    """
    try:
        from dawei.workspace.ip_workspace_service import ip_workspace_service as svc
        return await svc.get_portfolio_stats()
    except Exception as e:
        logger.exception("Failed to get portfolio stats")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# M7 资产仪表盘 — 报告导出
# ============================================================


@router.get("/ip/portfolio/{portfolio_id}/export")
async def export_portfolio_report(portfolio_id: str, format: str = "pdf"):
    """导出IP资产组合报告（PDF 或 Excel）"""
    result = await _get_ip_result(portfolio_id)
    if not result:
        # 降级：用实时聚合的 portfolio stats 生成报告
        try:
            from dawei.workspace.ip_workspace_service import ip_workspace_service as svc

            result = await svc.get_portfolio_stats()
        except Exception:
            result = {}
    if not result:
        raise HTTPException(status_code=404, detail=f"资产组合数据不存在: {portfolio_id}")
    if format == "excel":
        content = ip_exports.generate_portfolio_xlsx(result)
        return _file_response(
            content, f"portfolio-report-{portfolio_id}.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    # 默认 pdf
    content = ip_exports.generate_portfolio_pdf(result)
    return _file_response(content, f"portfolio-report-{portfolio_id}.pdf", "application/pdf")


# ============================================================
# M8 商标注册 — 商品清单 + 材料包 + 单文件导出
# ============================================================


@router.get("/ip/trademark/{trademark_id}/goods-list")
async def export_trademark_goods_list(trademark_id: str):
    """导出商标商品清单 Excel"""
    result = await _get_ip_result(trademark_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"商标结果不存在: {trademark_id}")
    content = ip_exports.generate_trademark_goods_xlsx(result)
    return _file_response(
        content, f"trademark-goods-{trademark_id}.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.get("/ip/trademark/{trademark_id}/package")
async def export_trademark_package(trademark_id: str):
    """导出商标申请材料包 ZIP（DOCX 材料 + 商品清单 Excel + 可注册性报告）"""
    result = await _get_ip_result(trademark_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"商标结果不存在: {trademark_id}")
    content = ip_exports.generate_trademark_package_zip(result)
    return _file_response(content, f"trademark-package-{trademark_id}.zip", "application/zip")


@router.get("/ip/trademark/{trademark_id}/material")
async def export_trademark_material(trademark_id: str):
    """导出商标申请材料单文件（DOCX）"""
    result = await _get_ip_result(trademark_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"商标结果不存在: {trademark_id}")
    content = ip_exports.generate_trademark_material_docx(result)
    return _file_response(
        content, f"trademark-material-{trademark_id}.docx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


# ============================================================
# POST /api/ip/upload — 文件上传
# ============================================================


@router.post("/ip/upload")
async def upload_ip_file(file: UploadFile = File(...)):
    """上传IP模块相关文件（技术文档、审查意见等）

    文件持久化到 {DAWEI_HOME}/uploads/{file_id}_{filename}。
    返回的 fileId 可用于后续 Agent 任务引用。
    """
    content = await file.read()
    size = len(content)
    max_size = get_settings().file_storage.max_file_size
    if size > max_size:
        raise HTTPException(
            status_code=413,
            detail=f"文件大小 {size} 字节超过限制 {max_size} 字节（{max_size // 1048576}MB）",
        )

    file_id = str(uuid.uuid4())

    # 持久化到文件系统
    from dawei import get_dawei_home

    upload_dir = get_dawei_home() / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    # 安全文件名：仅取 basename，防止路径穿越
    safe_name = Path(file.filename or "unnamed").name
    dest = upload_dir / f"{file_id}_{safe_name}"
    dest.write_bytes(content)

    logger.info(
        f"[IP Routes] File persisted: id={file_id} name={safe_name} "
        f"size={size} path={dest}"
    )

    return {
        "success": True,
        "data": {
            "fileId": file_id,
            "filename": file.filename,
            "size": size,
            "contentType": file.content_type,
            "path": str(dest),
        },
    }
