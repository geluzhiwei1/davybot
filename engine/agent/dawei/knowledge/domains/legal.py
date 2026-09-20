# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Legal domain profile for knowledge graph extraction"""

from .base import DomainProfile


class LegalProfile(DomainProfile):
    """法律领域画像，兼容各国立法、判例、监管与合同文书"""

    name = "legal"
    display_name = "法律"
    description = "全球法律文书知识图谱，适用于各国法规、判例、条约、监管文件、仲裁裁决、合同等场景"

    entity_types = {
        "LAW": "法律/法规/条例/规则/条约等规范性文件",
        "ARTICLE": "条/款/项/节/章/Part/Title/Section/Article/Clause",
        "CASE": "案例/判例/裁决/仲裁案件",
        "COURT": "法院/法庭/仲裁庭/审裁机构",
        "AGENCY": "立法机关/监管机构/行政机关/国际组织",
        "JURISDICTION": "国家/地区/州省/司法辖区",
        "ORG": "公司/机构/组织/政府部门",
        "PERSON": "自然人/当事人/法官/律师/证人",
        "CRIME": "罪名/违法行为/指控/违约事项",
        "CONTRACT": "合同/协议/条约/备忘录/许可证",
        "CLAUSE": "合同条款/约定/定义条款/免责条款",
        "EVIDENCE": "证据/证言/鉴定意见/附件",
        "REMEDY": "救济/处罚/禁令/赔偿/判罚",
    }

    relation_types = {
        "cites_law": "引用法规或规范性文件",
        "references_case": "引用案例/判例/裁决",
        "issued_by": "由其颁布/发布",
        "applies_to": "适用于对象/事项",
        "applies_in_jurisdiction": "适用于辖区",
        "governed_by": "受其管辖/约束",
        "violates": "违反/涉嫌违反",
        "judged_by": "由其审理/裁判",
        "appeals_to": "上诉/复审至",
        "interprets": "解释/适用/援引",
        "amends": "修订/替代/废止",
        "defines_crime": "规定犯罪/违法行为/违约责任",
        "party_to": "当事方/签署方",
        "supports": "作为证据支持",
        "imposes_remedy": "施加救济/处罚/义务",
    }

    dictionaries = {
        "offenses": [
            "fraud", "theft", "bribery", "embezzlement", "money laundering",
            "assault", "robbery", "kidnapping", "murder", "manslaughter",
            "诈骗罪", "盗窃罪", "受贿罪", "贪污罪", "洗钱罪", "故意伤害罪",
            "抢劫罪", "绑架罪", "故意杀人罪", "过失致人死亡罪",
        ],
        "courts": [
            "Supreme Court", "Constitutional Court", "High Court", "Court of Appeal",
            "District Court", "Tribunal", "Arbitral Tribunal", "最高人民法院",
            "高级人民法院", "中级人民法院", "基层人民法院", "国际法院",
        ],
        "agencies": [
            "Parliament", "Congress", "Commission", "Ministry of Justice",
            "仲裁委员会", "检察院", "司法部", "欧盟委员会",
        ],
    }

    dictionary_entity_map = {
        "offenses": "CRIME",
        "courts": "COURT",
        "agencies": "AGENCY",
    }

    patterns = {
        "provision_ref": [
            r"第[一二三四五六七八九十百千\d]+(?:条|款|项|节|章)",
            r"\b(?:Article|Section|Sec\.?|Clause|Paragraph|Para\.?|Part|Title|Chapter)\s+\d+[A-Za-z0-9()\-\.]*\b",
            r"\b(?:Art\.?|§)\s*\d+[A-Za-z0-9()\-\.]*\b",
        ],
        "law_name": [
            r"《[^》]+》",
            r"\b[A-Z][A-Za-z'&,\- ]+\s+(?:Act|Code|Regulation|Directive|Ordinance|Statute|Treaty|Convention|Constitution)\b",
        ],
        "case_no": [
            r"[（(]\d{4}[）)].*?号",
            r"\b(?:Case|Claim|Appeal|Docket|File|Suit|Writ|Petition|Application|Proceeding)\s*(?:No\.?|Number)?\s*[:#]?\s*[A-Za-z0-9./_\-]+\b",
        ],
        "tribunal_name": [
            r"\b(?:Supreme|Constitutional|Federal|High|Appellate|District|Circuit|Commercial|Administrative|Tax|Family|Labor|Employment|Immigration)\s+(?:Court|Tribunal)\b",
            r"\b(?:International Court of Justice|European Court of Human Rights|International Criminal Court|WTO Appellate Body|ICSID Tribunal)\b",
        ],
    }

    pattern_entity_map = {
        "provision_ref": "ARTICLE",
        "law_name": "LAW",
        "case_no": "CASE",
        "tribunal_name": "COURT",
    }

    extraction_prompt = """你是一个专业的国际法律知识图谱构建助手。请从以下法律文书中提取实体和关系。

文本内容：
{text}

请严格按照以下JSON格式返回，不要添加任何其他内容：

{{
    "entities": [
        {{"name": "实体名称", "type": "类型", "properties": {{"key": "value"}}}}
    ],
    "relations": [
        {{"from_entity": "实体1", "to_entity": "实体2", "relation_type": "关系类型", "properties": {{}}}}
    ]
}}

实体类型：{entity_types}
关系类型：{relation_types}

注意：
1. 输入可能来自任何国家、地区或国际组织，可能属于大陆法、普通法、国际法、仲裁规则或行业监管规则；不得默认套用中国法结构。
2. 必须保留原文中的正式名称与原始语言，例如法律标题、法院名称、机构名称、案件编号、合同名称、条约名称。
3. 对规范性文件内部结构要按原文精确提取，包括条、款、项、节、章，以及 Article/Section/Clause/Part/Title 等编号。
4. 当文本涉及司法辖区、颁布机关、审理机构、当事方、救济措施、违法/犯罪指控、证据材料时，应优先提取并建立明确关系。
5. 仅提取文本中明确出现或可直接确定的实体与关系；不要根据单一法域常识补全隐含事实。
6. 如果同一概念存在不同法域叫法，应保留原文表述，并可在 properties 中补充 role、jurisdiction、citation、document_type、language 等信息。
"""
