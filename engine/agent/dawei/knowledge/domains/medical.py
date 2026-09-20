# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Medical domain profile for knowledge graph extraction"""

from .base import DomainProfile


class MedicalProfile(DomainProfile):
    """医学领域画像，适用于病历、医学文献、药品说明书等"""

    name = "medical"
    display_name = "医学"
    description = "医学领域知识图谱，适用于病历、医学文献、药品说明书等场景"

    entity_types = {
        "DISEASE": "疾病",
        "SYMPTOM": "症状",
        "DRUG": "药物",
        "PROCEDURE": "手术/操作",
        "ANATOMY": "解剖部位",
        "TEST": "检查指标",
        "PATHOLOGY": "病理",
        "TREATMENT": "治疗方案",
    }

    relation_types = {
        "treats": "治疗",
        "causes": "引起",
        "contraindicates": "禁忌",
        "dosage_of": "剂量",
        "complication_of": "并发症",
        "indicates": "指示",
        "side_effect": "副作用",
    }

    dictionaries = {
        "drugs": [
            "阿司匹林", "布洛芬", "对乙酰氨基酚", "青霉素", "头孢",
            "阿莫西林", "红霉素", "左氧氟沙星", "甲硝唑",
            "奥美拉唑", "雷尼替丁", "地塞米松", "泼尼松",
            "硝苯地平", "氨氯地平", "二甲双胍", "胰岛素",
            "阿托伐他汀", "华法林", "肝素",
        ],
        "abbreviations": [
            "BP", "HR", "FDA", "ICD", "CT", "MRI", "ECG", "EEG",
            "B超", "X光", "PET", "WBC", "RBC", "HGB", "PLT",
        ],
    }

    patterns = {
        "dosage": [r"\d+\.?\d*\s*(mg|ml|g|μg|IU|U)"],
        "lab_value": [r"[A-Z]+[:：]\s*\d+\.?\d*"],
    }

    extraction_prompt = """你是一个专业的医学知识图谱构建助手。请从以下医学文本中提取实体和关系。

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
1. 医学术语必须精确提取，注意区分疾病、症状和体征
2. 药物剂量必须精确（如"5mg/kg"）
3. 疾病-症状-治疗的关系链要完整
4. 只提取文本中明确提到的实体和关系
"""
