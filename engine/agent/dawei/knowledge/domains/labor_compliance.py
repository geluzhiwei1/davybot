# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Overseas labor & employment compliance domain profile for knowledge graph extraction.

Designed to process:
- Cross-border employment contracts and secondment agreements
- Work permit / visa applications and immigration rules
- Host country labor laws (minimum wage, working hours, leave entitlements)
- Social security / pension bilateral agreements and contribution obligations
- Anti-forced-labor / human trafficking compliance requirements
- Collective bargaining agreements and trade union regulations
- Occupational health & safety (OHS) standards and incident reports
- Employment dispute adjudication records (labor tribunals, arbitration, court rulings)
- Multi-national employer obligations: payroll, tax withholding, EOR/PEO structures

Scope: outbound Chinese employees and globally mobile workforce operating in
any foreign jurisdiction, as well as inbound foreign workers employed in China.
"""

from .base import DomainProfile


class LaborComplianceProfile(DomainProfile):
    """海外劳动用工法律合规领域画像

    覆盖跨境用工合同、工作许可/签证、东道国劳工法律、社保双边协议、
    强迫劳动合规、集体谈判协议、职业安全健康、劳动争议裁决，
    以及跨国雇主薪资/税务/EOR结构等场景。
    """

    name = "labor_compliance"
    display_name = "海外劳动用工合规"
    description = (
        "海外劳动用工法律合规知识图谱，适用于跨境派遣合同、工作许可审批、"
        "东道国劳工法规、社会保险双边协议、强迫劳动尽职调查、集体谈判协议、"
        "职业安全健康报告及劳动争议仲裁/诉讼等场景"
    )

    # ------------------------------------------------------------------ #
    # Entity types                                                         #
    # ------------------------------------------------------------------ #
    entity_types = {
        # Parties
        "EMPLOYER": "雇主/用人单位/派遣方/东道国企业/EOR/PEO",
        "EMPLOYEE": "受雇人/外派员工/境外劳工/当事自然人",
        "WORKER_GROUP": "劳动者集体/工会/工人代表委员会/工会联合会",
        "AGENCY": "劳务中介机构/人力资源服务商/猎头公司/招聘中介",
        "AUTHORITY": "劳工监管机构/移民局/社保机构/职业安全局/税务机关",
        "COURT": "劳动法院/劳动仲裁庭/行政法庭/上诉法院",
        # Legal instruments
        "LAW": "劳工法律/法规/指令/条例/实施细则/国家标准",
        "CONTRACT": "劳动合同/派遣协议/EOR协议/服务协议/集体谈判协议",
        "CLAUSE": "合同条款/约定/终止条款/竞业限制/保密条款",
        "PERMIT": "工作许可/居留许可/签证/劳工配额批文",
        "CERTIFICATE": "合规证书/豁免证明/社保缴纳证明/安全资质证书",
        "CASE": "劳动争议案件/仲裁案件/诉讼/行政处罚案",
        "POLICY": "企业人力资源政策/派遣政策/薪酬政策/平等就业政策",
        # Geographic / jurisdictional
        "JURISDICTION": "国家/地区/州省/经济特区/司法辖区",
        "WORKPLACE": "工作地点/项目工地/办公地址/施工现场",
        # Obligations & entitlements
        "OBLIGATION": "法定义务/合规要求/申报义务/告知义务",
        "ENTITLEMENT": "法定权利/最低工资/带薪休假/加班工资/生育权利",
        "BENEFIT": "福利/社会保险/年金/医疗/工伤赔偿",
        "VIOLATION": "违规行为/违约/违法用工/强迫劳动/歧视/骚扰",
        "PENALTY": "罚款/行政处罚/刑事责任/赔偿/吊销许可",
        # Supporting entities
        "DOCUMENT": "护照/证件/薪资单/工时记录/入职材料",
        "STANDARD": "ILO公约/国际劳工标准/行业自律准则/CSR规范",
    }

    # ------------------------------------------------------------------ #
    # Relation types                                                       #
    # ------------------------------------------------------------------ #
    relation_types = {
        # Employment relationship
        "employs": "雇用/聘用劳动者",
        "seconded_to": "派遣至东道国/接收方",
        "contracted_via": "通过中介/EOR/PEO雇用",
        "represented_by": "由工会/律师/代理人代理",
        # Regulatory / compliance
        "regulated_by": "受其监管/审批/审查",
        "governed_by": "受其法律/协议约束",
        "issued_by": "由其颁布/发布/批准",
        "applies_in": "适用于辖区/行业",
        "requires_permit": "需申请该许可证/签证",
        "holds_permit": "持有该许可证/签证/证书",
        "complies_with": "符合/遵从该标准或规定",
        "violates": "违反/涉嫌违反",
        # Contractual
        "party_to": "为合同/协议当事方",
        "governed_by_contract": "受该合同/条款约束",
        "contains_clause": "包含该条款",
        "amends": "修订/补充/替代该合同或法规",
        # Entitlement & obligation
        "entitled_to": "依法/依约享有该权利/待遇",
        "obligated_to": "依法/依约承担该义务",
        "contributes_to": "缴纳该社保/年金/基金",
        "covered_by": "受该保险/协议/计划覆盖",
        # Dispute & enforcement
        "disputes_with": "与其发生劳动争议",
        "adjudicated_by": "由其仲裁/审判",
        "appeals_to": "就该裁决上诉至",
        "penalized_by": "被其处罚/处分",
        "imposes_penalty": "对其施加处罚/赔偿",
        # Geographic
        "located_in": "位于/注册于辖区",
        "operates_in": "在该辖区运营/派遣",
    }

    # ------------------------------------------------------------------ #
    # Dictionaries — seed terms for rule-based matching                   #
    # ------------------------------------------------------------------ #
    dictionaries = {
        "labor_authorities": [
            # International
            "ILO", "International Labour Organization", "国际劳工组织",
            # US
            "EEOC", "Equal Employment Opportunity Commission",
            "NLRB", "National Labor Relations Board",
            "DOL", "US Department of Labor",
            "OSHA", "Occupational Safety and Health Administration",
            # EU / European
            "European Labour Authority", "ELA",
            "European Foundation for the Improvement of Living and Working Conditions",
            # UK
            "ACAS", "UK Employment Tribunal",
            "Health and Safety Executive", "HSE",
            # Asia-Pacific
            "Ministry of Manpower", "MOM",        # Singapore
            "Ministry of Labour", "劳动部",
            "人力资源和社会保障部", "人社部",
            "国家移民管理局",
            # Middle East / GCC
            "Ministry of Human Resources and Emiratisation", "MOHRE",
            "Saudi Ministry of Human Resources",
        ],
        "permit_types": [
            # Generic
            "work permit", "work visa", "employment authorization",
            "labor card", "residency permit", "blue card",
            "工作许可证", "就业许可", "外国人工作许可",
            # Country-specific
            "H-1B", "H-2A", "H-2B", "L-1", "O-1", "E-3",   # US
            "Tier 2 visa", "Skilled Worker visa",              # UK
            "EU Blue Card",
            "Employment Pass", "S Pass", "Work Permit",        # Singapore
            "就业签证", "商务签证", "居留许可",
        ],
        "labor_standards": [
            # ILO Core Conventions
            "ILO C29", "ILO C87", "ILO C98", "ILO C100",
            "ILO C105", "ILO C111", "ILO C138", "ILO C182",
            "ILO Convention No. 29", "ILO Convention No. 87",
            "Forced Labour Convention", "Freedom of Association Convention",
            "Right to Organise Convention", "Equal Remuneration Convention",
            "Abolition of Forced Labour Convention",
            "Discrimination (Employment and Occupation) Convention",
            "Minimum Age Convention", "Worst Forms of Child Labour Convention",
            # Multi-stakeholder / CSR
            "UN Global Compact", "UNGP", "UN Guiding Principles",
            "OECD Guidelines for Multinational Enterprises",
            "SA8000", "ISO 45001", "ISO 26000",
            "RBA Code of Conduct", "Responsible Business Alliance",
            # Forced labor / supply chain
            "Uyghur Forced Labor Prevention Act", "UFLPA",
            "UK Modern Slavery Act", "Australia Modern Slavery Act",
            "German Supply Chain Act", "Lieferkettensorgfaltspflichtengesetz",
            "EU Corporate Sustainability Due Diligence Directive", "CSDDD",
        ],
        "contract_types": [
            "employment contract", "labor contract", "secondment agreement",
            "service agreement", "EOR agreement", "PEO agreement",
            "collective bargaining agreement", "CBA",
            "fixed-term contract", "indefinite-term contract",
            "zero-hours contract", "agency worker agreement",
            "劳动合同", "劳务合同", "派遣协议", "集体合同",
            "劳务派遣协议", "雇主责任协议",
        ],
        "violation_types": [
            # Forced / child labor
            "forced labor", "forced labour", "child labor", "child labour",
            "debt bondage", "human trafficking", "labor trafficking",
            "强迫劳动", "童工", "人口贩卖", "债务劳役",
            # Wage & hour
            "wage theft", "unpaid wages", "minimum wage violation",
            "overtime violation", "working hours violation",
            "欠薪", "克扣工资", "拖欠工资", "超时加班",
            # Discrimination & harassment
            "discrimination", "harassment", "sexual harassment",
            "wrongful dismissal", "unfair dismissal", "constructive dismissal",
            "就业歧视", "性骚扰", "非法解雇", "违法辞退",
            # Safety
            "workplace accident", "occupational disease",
            "safety violation", "OHS breach",
            "工伤事故", "职业病", "安全违规",
        ],
        "social_security_terms": [
            "social security", "social insurance", "pension", "superannuation",
            "health insurance", "workers compensation", "unemployment insurance",
            "totalization agreement", "bilateral social security agreement",
            "社会保险", "养老保险", "医疗保险", "工伤保险",
            "失业保险", "生育保险", "社保双边协议", "社保豁免",
        ],
    }

    dictionary_entity_map = {
        "labor_authorities": "AUTHORITY",
        "permit_types": "PERMIT",
        "labor_standards": "STANDARD",
        "contract_types": "CONTRACT",
        "violation_types": "VIOLATION",
        "social_security_terms": "BENEFIT",
    }

    # ------------------------------------------------------------------ #
    # Patterns — regex for identifiers common in labor compliance docs    #
    # ------------------------------------------------------------------ #
    patterns = {
        # Work permit / visa reference numbers
        "permit_number": [
            r"\b(?:Work\s+Permit|Employment\s+Pass|EP|SP|WP)\s*(?:No\.?|Number|#)?\s*[A-Z0-9\-]{4,20}\b",
            r"\b外国人工作许可证?编号\s*[:：]?\s*[A-Z0-9\-]{6,20}\b",
        ],
        # ILO convention reference
        "ilo_convention": [
            r"\bILO\s+(?:Convention\s+)?(?:No\.?\s*)?\d{1,3}\b",
            r"\bC\d{1,3}\b",   # short form C87, C98 etc.
        ],
        # Legal provision reference (reuse cross-language patterns)
        "provision_ref": [
            r"第[一二三四五六七八九十百千\d]+(?:条|款|项|节|章)",
            r"\b(?:Article|Section|Sec\.?|Clause|Para(?:graph)?\.?|Part|Title|Chapter)\s+\d+[A-Za-z0-9()\-\.]*\b",
            r"\b(?:Art\.?|§)\s*\d+[A-Za-z0-9()\-\.]*\b",
        ],
        # Law / regulation name
        "law_name": [
            r"《[^》]+》",
            r"\b[A-Z][A-Za-z'&,\- ]+\s+(?:Act|Code|Law|Regulation|Directive|Ordinance|Decree|Convention|Treaty)\b",
        ],
        # Case / arbitration / complaint reference number
        "case_no": [
            r"[（(]\d{4}[）)].*?号",
            r"\b(?:Case|Claim|Complaint|Docket|File|Award|Reference)\s*(?:No\.?|Number)?\s*[:#]?\s*[A-Za-z0-9./_\-]+\b",
        ],
        # Wage / salary figures (useful for minimum wage compliance)
        "wage_figure": [
            r"\b(?:USD|EUR|GBP|SGD|AED|AUD|JPY|CNY|RMB)\s*[\d,]+(?:\.\d{1,2})?\b",
            r"\b[\d,]+(?:\.\d{1,2})?\s*(?:per\s+(?:hour|day|month|week)|/(?:hr|h|day|month|mo|week|wk))\b",
            r"\b最低工资\s*[:：]?\s*[\d,]+(?:\.\d{1,2})?\s*(?:元|人民币|RMB|CNY)?\b",
        ],
        # Working hours / overtime thresholds
        "hours_figure": [
            r"\b\d{1,3}\s*(?:hours?|小时)\s*(?:per\s+(?:week|day|month)|每(?:周|天|月))\b",
            r"\b(?:overtime|加班)\s*(?:exceeds?|超过)\s*\d+\s*(?:hours?|小时)\b",
        ],
        # Social security contribution rate
        "contribution_rate": [
            r"\b\d{1,3}(?:\.\d{1,2})?\s*%\s*(?:employer|employee|雇主|雇员|个人|单位)\s*(?:contribution|缴费|缴纳率)\b",
            r"\b(?:employer|employee|雇主|雇员)\s*(?:contribution|缴费)\s*(?:rate|比例|率)\s*[:：]?\s*\d{1,3}(?:\.\d{1,2})?\s*%\b",
        ],
        # Passport / national ID (for worker identity)
        "worker_id": [
            r"\b[A-Z]{1,2}\d{6,9}\b",                    # passport
            r"\b\d{15}(?:\d{3})?\b",                      # Chinese national ID
        ],
    }

    pattern_entity_map = {
        "permit_number": "PERMIT",
        "ilo_convention": "STANDARD",
        "provision_ref": "CLAUSE",
        "law_name": "LAW",
        "case_no": "CASE",
        "wage_figure": "ENTITLEMENT",
        "hours_figure": "ENTITLEMENT",
        "contribution_rate": "BENEFIT",
        "worker_id": "DOCUMENT",
    }

    # ------------------------------------------------------------------ #
    # LLM extraction prompt                                                #
    # ------------------------------------------------------------------ #
    extraction_prompt = """你是一名专业的海外劳动用工法律合规知识图谱构建助手。你的任务是从以下文本中提取与跨境用工合规相关的实体和关系。

文本内容：
{text}

请严格按照以下JSON格式返回，不要添加任何其他内容：

{{
    "entities": [
        {{
            "name": "实体名称（保留原文语言和官方名称）",
            "type": "类型",
            "properties": {{
                "jurisdiction": "所属国家/地区/辖区",
                "language": "原文语言",
                "effective_date": "生效日期",
                "expiry_date": "到期/失效日期",
                "document_type": "文件类型/文书性质",
                "reference_no": "编号/案号/许可证号",
                "description": "简要说明（可选）"
            }}
        }}
    ],
    "relations": [
        {{
            "from_entity": "实体1",
            "to_entity": "实体2",
            "relation_type": "关系类型",
            "properties": {{
                "start_date": "关系开始日期",
                "end_date": "关系结束日期",
                "jurisdiction": "适用辖区",
                "role": "具体角色/职务（如有）",
                "amount": "金额/费率/比例（如有）",
                "source": "信息来源"
            }}
        }}
    ]
}}

实体类型：{entity_types}
关系类型：{relation_types}

提取规则：
1. 【当事方识别】优先提取雇主（EMPLOYER）、劳动者（EMPLOYEE）、劳务中介（AGENCY）、监管机构（AUTHORITY）及工会（WORKER_GROUP），并明确相互间的雇用、派遣、监管关系。
2. 【法律文件】识别适用的东道国劳工法律/法规（LAW）、合同/协议（CONTRACT）、国际劳工标准（STANDARD），并提取具体条款（CLAUSE）及条文编号。
3. 【许可证/证件】提取工作许可、居留签证、社保缴纳证书等（PERMIT / CERTIFICATE）及其编号、颁发机构、有效期。
4. 【权利义务】识别法定最低工资、工时限制、带薪休假、加班费等劳动权利（ENTITLEMENT），以及雇主申报、缴纳社保、OHS整改等合规义务（OBLIGATION）。
5. 【社会保险】提取社保缴纳比例、双边社保协议及豁免安排（BENEFIT），明确缴纳方（雇主/雇员）及适用辖区。
6. 【违规与处罚】识别违规行为（VIOLATION）——包括强迫劳动、童工、欠薪、超时加班、就业歧视、职业安全违规——及相应处罚（PENALTY）。
7. 【争议与裁决】提取劳动争议案件（CASE）、仲裁/法院裁决，明确争议方、裁决机构、裁决结果和赔偿金额。
8. 【地理信息】标注所有国家/地区/辖区（JURISDICTION）及工作地点（WORKPLACE），用于判断适用法律。
9. 【名称保留】保留原文官方名称、缩写及编号（如 ILO C87、H-1B、UFLPA），不要翻译或简化。
10. 【不确定信息】置信度低的实体或关系在 properties 中注明 "confidence": "low" 或 "source": "inferred"。
11. 仅提取文本中明确出现或可直接推断的信息，不要凭借背景知识补全未提及的事实。
"""
