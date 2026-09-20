# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Research domain profile for knowledge graph extraction"""

from .base import DomainProfile


class ResearchProfile(DomainProfile):
    """科研领域画像，适用于论文、学术文献、专利等"""

    name = "research"
    display_name = "科研"
    description = "科研领域知识图谱，适用于论文、学术文献、专利等场景"

    entity_types = {
        "PAPER": "论文",
        "AUTHOR": "作者",
        "INSTITUTION": "机构",
        "METHOD": "方法",
        "DATASET": "数据集",
        "FORMULA": "公式",
        "CONCEPT": "概念",
        "RESULT": "结果",
        "TOOL": "工具",
    }

    relation_types = {
        "cites": "引用",
        "based_on": "基于",
        "proposes": "提出",
        "validates": "验证",
        "improves": "改进",
        "uses_method": "使用方法",
        "authored_by": "作者",
    }

    dictionaries = {
        "methods": [
            "RNN", "CNN", "LSTM", "GRU", "Transformer", "Attention",
            "BERT", "GPT", "ResNet", "VGG", "YOLO", "GAN",
            "VAE", "Diffusion", "RLHF", "SFT", "LoRA", "PEFT",
            "Fine-tuning", "Pre-training", "Self-supervised",
            "Cross-validation", "A/B testing", "Bayesian",
        ],
        "datasets": [
            "ImageNet", "COCO", "MNIST", "CIFAR", "SQuAD", "GLUE",
            "SuperGLUE", "WikiText", "Pile", "RedPajama",
        ],
    }

    patterns = {
        "citation_bracket": [r"\[\d+\]"],
        "citation_author_year": [r"\([A-Z][a-z]+,\s*\d{4}\)"],
        "doi": [r"10\.\d{4,}/\S+"],
    }

    extraction_prompt = """你是一个专业的科研知识图谱构建助手。请从以下学术文本中提取实体和关系。

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
1. 方法论名称要精确提取（如"Transformer"、"BERT"）
2. 引用关系要标注清楚来源
3. 实验结果要包含关键数值
4. 只提取文本中明确提到的实体和关系
"""
