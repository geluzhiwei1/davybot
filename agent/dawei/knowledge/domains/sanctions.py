# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Sanctions & financial crime domain profile for knowledge graph extraction.

Entity model strictly aligned with OpenSanctions FollowTheMoney (FtM) schema:

FtM ontology hierarchy (used subset):
    Thing
    ├── LegalEntity
    │   ├── Person
    │   └── Organization
    │       ├── Company  (also extends Asset)
    │       └── PublicBody
    ├── Address
    ├── Position
    ├── CryptoWallet  (also extends Value)
    ├── Security      (also extends Asset)
    └── Article
    Interval
    ├── Sanction
    ├── Ownership      (also extends Interest)
    ├── Directorship   (also extends Interest)
    ├── Membership     (also extends Interest)
    ├── Employment     (also extends Interest)
    ├── Representation (also extends Interest)
    ├── Succession     (also extends Interest)
    ├── Occupancy
    ├── Family
    ├── Associate
    ├── Payment        (also extends Value)
    ├── Debt           (also extends Value)
    ├── Documentation  (also extends Interest)
    └── Identification
        └── Passport
"""

from .base import DomainProfile


class SanctionsProfile(DomainProfile):
    """制裁及金融犯罪领域画像

    覆盖制裁指定文件、PEP 数据、合规监管名单、反洗钱/反恐融资报告、
    受益所有权文件及国际调查性新闻（ICIJ/OCCRP）等场景。

    实体与关系模型严格对齐 OpenSanctions FollowTheMoney (FtM) 本体：
    """

    name = "sanctions"
    display_name = "制裁 & 合规"
    description = (
        "制裁、PEP 及金融犯罪知识图谱，适用于 OFAC/UN/EU/UK 制裁名单、"
        "反洗钱报告、受益所有权穿透分析及国际调查性新闻等场景"
    )

    # ------------------------------------------------------------------ #
    # Entity types — 1:1 aligned with FtM schema                         #
    # ------------------------------------------------------------------ #
    # Grouped by FtM inheritance: Thing-based (real-world objects) vs
    # Interval-based (time-bounded events/relationships).
    entity_types = {
        # --- Thing > LegalEntity (natural persons & legal persons) --------
        "Person": "自然人 (FtM: Person)",
        "Organization": "组织/机构 (FtM: Organization, 非公司制)",
        "Company": "公司/企业/信托/基金 (FtM: Company, 含 Asset)",
        "PublicBody": "公共机构/政府部门/国有企业 (FtM: PublicBody)",
        # --- Thing > others ----------------------------------------------
        "Address": "地址/注册地 (FtM: Address)",
        "Position": "政治/公职职务 (FtM: Position)",
        "CryptoWallet": "加密货币钱包/地址 (FtM: CryptoWallet)",
        "Security": "证券/金融工具 (FtM: Security)",
        # --- Interval > Sanction -----------------------------------------
        "Sanction": "制裁指定记录 (FtM: Sanction)",
        # --- Interval > Interest (corporate / legal relations) -----------
        "Ownership": "股权/受益所有权 (FtM: Ownership)",
        "Directorship": "董事/高管任命 (FtM: Directorship)",
        "Membership": "成员/附属关系 (FtM: Membership)",
        "Employment": "雇佣/任职关系 (FtM: Employment)",
        "Representation": "代理/中间人关系 (FtM: Representation)",
        "Succession": "法律继承关系 (FtM: Succession)",
        "Documentation": "文件/证据关联 (FtM: Documentation)",
        # --- Interval > others -------------------------------------------
        "Occupancy": "职务担任记录 (FtM: Occupancy, Person→Position)",
        "Family": "家庭亲属关系 (FtM: Family)",
        "Associate": "非家庭关联人关系 (FtM: Associate)",
        "Payment": "资金转移/付款 (FtM: Payment)",
        "Debt": "债权债务 (FtM: Debt)",
        # --- Interval > Identification -----------------------------------
        "Identification": "身份证件 (FtM: Identification, 通用)",
        "Passport": "护照 (FtM: Passport, Identification 子类型)",
        # --- Thing > Vehicle subtree -------------------------------------
        "Vessel": "船舶/船只 (FtM: Vessel)",
        "Airplane": "飞机/航空器 (FtM: Airplane)",
    }

    # ------------------------------------------------------------------ #
    # Relation types — derived from FtM interstitial entity edge         #
    # semantics. Each relation maps to the corresponding FtM property    #
    # on the interstitial (Interval-based) entity.                       #
    # ------------------------------------------------------------------ #
    relation_types = {
        # --- Sanction edges (Sanction → Thing) ---------------------------
        "sanctioned":     "被制裁指定 (Sanction:entity → 被制裁主体)",
        # --- Corporate structure (Interest edges) ------------------------
        "owns":           "持有股权/受益所有 (Ownership:owner → Ownership:asset)",
        "directed_by":    "担任董事/高管 (Directorship:director → Directorship:organization)",
        "member_of":      "成员/附属 (Membership:member → Membership:organization)",
        "employed_by":    "受雇于 (Employment:employee → Employment:employer)",
        "represents":     "代理/中介 (Representation:agent → Representation:client)",
        "successor_of":   "法律继承 (Succession:successor → Succession:predecessor)",
        "documented_in":  "文件关联 (Documentation:entity → Documentation:document)",
        # --- Political exposure (Occupancy edges) -----------------------
        "holds_position": "担任职务 (Occupancy:holder → Occupancy:post)",
        # --- Personal relations (Interval edges) -------------------------
        "family_of":      "家庭亲属 (Family:person → Family:relative)",
        "associate_of":   "非家庭关联 (Associate:person → Associate:associate)",
        # --- Financial flows (Payment / Debt edges) ----------------------
        "paid_to":        "付款 (Payment:payer → Payment:beneficiary)",
        "owes_to":        "欠款 (Debt:debtor → Debt:creditor)",
        # --- Identity (Identification edges) -----------------------------
        "identified_by":  "持证件 (Identification:holder ← Identification)",
        # --- Position → Organization (Position edges) -------------------
        "position_in":    "职务所属机构 (Position:organization)",
        # --- Thing → Address (Thing:addressEntity) ----------------------
        "located_at":     "位于/注册于 (Thing:addressEntity → Address)",
        # --- Ownership detail edges (supplementary) ---------------------
        "owns_asset":     "持有/控制资产 (Ownership:owner → Asset)",
        "operates_vessel":"运营/控制船舶 (Ownership:owner → Vessel)",
    }

    # ------------------------------------------------------------------ #
    # FtM property schema per entity type                                 #
    # Used by extraction_prompt to guide LLM toward correct FtM fields.  #
    # Format: { ftm_property: brief_description }                        #
    # Only lists domain-relevant properties (not all FtM properties).    #
    # ------------------------------------------------------------------ #
    entity_properties = {
        "Person": {
            "name": "姓名（保留原文）",
            "alias": "别名/化名",
            "previousName": "曾用名",
            "weakAlias": "模糊别名（不用于匹配）",
            "country": "关联国家",
            "nationality": "国籍 (country code)",
            "citizenship": "公民身份 (country code)",
            "birthDate": "出生日期",
            "birthPlace": "出生地",
            "birthCountry": "出生国 (country code)",
            "deathDate": "死亡日期",
            "gender": "性别",
            "title": "头衔/称谓",
            "firstName": "名/given name",
            "lastName": "姓/surname",
            "position": "职位",
            "idNumber": "身份证号",
            "passportNumber": "护照号码",
            "taxNumber": "税号",
            "email": "电子邮箱",
            "phone": "电话号码",
            "topics": "风险标签 (sanction/role.pep/role.rca/crime.*)",
            "sourceUrl": "信息来源链接",
        },
        "Company": {
            "name": "公司名称（保留原文）",
            "alias": "别名/商号",
            "previousName": "曾用名",
            "country": "关联国家",
            "mainCountry": "主要国家 (country code)",
            "jurisdiction": "注册辖区 (country code)",
            "registrationNumber": "注册号",
            "legalForm": "法律形式（LLC/GmbH等）",
            "incorporationDate": "成立日期",
            "dissolutionDate": "注销/解散日期",
            "status": "状态 (Active/Dissolved/etc.)",
            "sector": "行业",
            "classification": "分类",
            "idNumber": "证件号码",
            "taxNumber": "税号",
            "vatCode": "VAT税号",
            "leiCode": "LEI法人识别符",
            "dunsCode": "DUNS编码",
            "uscCode": "统一社会信用代码",
            "innCode": "INN俄罗斯税号",
            "ogrnCode": "OGRN俄罗斯注册号",
            "swiftBic": "SWIFT/BIC银行代码",
            "ticker": "股票代码",
            "opencorporatesUrl": "OpenCorporates链接",
            "email": "电子邮箱",
            "phone": "电话号码",
            "website": "网站",
            "topics": "风险标签",
            "sourceUrl": "信息来源链接",
        },
        "Organization": {
            "name": "组织名称",
            "alias": "别名",
            "country": "关联国家",
            "mainCountry": "主要国家",
            "cageCode": "CAGE商业及政府实体代码",
            "permId": "PermID (LSEG/Refinitiv)",
            "imoNumber": "IMO编号",
            "giiNumber": "GIIN全球中介识别号",
            "topics": "风险标签",
            "sourceUrl": "信息来源链接",
        },
        "PublicBody": {
            "name": "公共机构名称",
            "alias": "别名",
            "country": "关联国家",
            "mainCountry": "主要国家",
            "jurisdiction": "辖区",
            "subnationalArea": "地方管辖区名称/代码",
            "topics": "风险标签",
            "sourceUrl": "信息来源链接",
        },
        "Vessel": {
            "name": "船名",
            "alias": "曾用名/别名",
            "country": "关联国家",
            "flag": "船旗国 (country code)",
            "pastFlags": "历史船旗国",
            "imoNumber": "IMO编号 (format: imo)",
            "mmsi": "MMSI海上移动服务标识",
            "callSign": "呼号",
            "registrationNumber": "注册号",
            "tonnage": "吨位",
            "grossRegisteredTonnage": "总登记吨位",
            "deadweightTonnage": "载重吨位",
            "buildDate": "建造日期",
            "type": "船型",
            "model": "型号",
            "topics": "风险标签",
            "sourceUrl": "信息来源链接",
        },
        "Airplane": {
            "name": "飞机名称/航班号",
            "country": "关联国家",
            "registrationNumber": "注册号",
            "serialNumber": "序列号",
            "type": "机型",
            "model": "型号",
            "buildDate": "制造日期",
            "topics": "风险标签",
            "sourceUrl": "信息来源链接",
        },
        "CryptoWallet": {
            "name": "钱包标签/名称",
            "publicKey": "公钥/钱包地址",
            "accountId": "账户ID",
            "managingExchange": "托管交易所",
            "holder": "持有人 (LegalEntity)",
            "currency": "币种",
            "balance": "余额",
            "topics": "风险标签",
            "sourceUrl": "信息来源链接",
        },
        "Security": {
            "name": "证券名称",
            "isin": "ISIN国际证券识别码 (format: isin)",
            "ticker": "股票代码",
            "figiCode": "FIGI金融工具全球标识 (format: figi)",
            "registrationNumber": "注册号",
            "issuer": "发行人 (LegalEntity)",
            "issueDate": "发行日期",
            "maturityDate": "到期日期",
            "type": "证券类型",
            "classification": "分类",
            "amount": "金额",
            "currency": "货币",
            "topics": "风险标签",
            "sourceUrl": "信息来源链接",
        },
        "Sanction": {
            "entity": "被制裁主体 (Thing)",
            "authority": "制裁发起机构",
            "authorityId": "机构标识号",
            "unscId": "UN SC标识号",
            "program": "制裁项目/名单",
            "programId": "项目编号",
            "programUrl": "项目链接",
            "provisions": "制裁范围/措施",
            "status": "状态 (Active/Lapsed/etc.)",
            "reason": "制裁原因",
            "country": "制裁发起国 (country code)",
            "startDate": "制裁开始日期",
            "endDate": "制裁结束日期",
            "listingDate": "列入日期",
            "duration": "持续时间",
            "sourceUrl": "信息来源链接",
            "publisher": "发布来源",
        },
        "Address": {
            "full": "完整地址",
            "street": "街道地址",
            "city": "城市",
            "state": "州/省",
            "postalCode": "邮编",
            "region": "地区",
            "country": "国家 (country code)",
            "remarks": "备注（如 c/o）",
            "postOfficeBox": "邮政信箱",
        },
        "Position": {
            "name": "职务名称",
            "organization": "所属组织 (Organization)",
            "country": "国家",
            "subnationalArea": "地方管辖区",
            "inceptionDate": "职务设立日期",
            "dissolutionDate": "职务废止日期",
        },
        "Identification": {
            "holder": "持证人 (LegalEntity)",
            "type": "证件类型",
            "country": "签发国 (country code)",
            "number": "证件号码",
            "authority": "签发机关",
            "startDate": "生效日期",
            "endDate": "到期日期",
        },
        "Passport": {
            "holder": "持证人 (LegalEntity)",
            "type": "证件类型",
            "country": "签发国 (country code)",
            "number": "护照号码",
            "authority": "签发机关",
            "startDate": "生效日期",
            "endDate": "到期日期",
        },
        "Ownership": {
            "owner": "所有者 (LegalEntity)",
            "asset": "被持有资产 (Asset/Company)",
            "percentage": "持股比例",
            "sharesCount": "股份数量",
            "sharesValue": "股份价值",
            "sharesCurrency": "股份币种",
            "ownershipType": "所有权类型",
            "startDate": "关系开始日期",
            "endDate": "关系结束日期",
            "role": "角色",
            "status": "状态",
        },
        "Directorship": {
            "director": "董事/高管 (LegalEntity)",
            "organization": "机构 (Organization)",
            "role": "角色/职位",
            "status": "状态",
            "startDate": "任命日期",
            "endDate": "离任日期",
        },
        "Membership": {
            "member": "成员 (LegalEntity)",
            "organization": "组织 (Organization)",
            "role": "角色",
            "status": "状态",
            "startDate": "加入日期",
            "endDate": "退出日期",
        },
        "Employment": {
            "employee": "员工 (Person)",
            "employer": "雇主 (Organization)",
            "role": "角色/职位",
            "status": "状态",
            "startDate": "入职日期",
            "endDate": "离职日期",
        },
        "Representation": {
            "agent": "代理人/中间人 (LegalEntity)",
            "client": "委托人 (LegalEntity)",
            "role": "角色",
            "status": "状态",
            "startDate": "代理开始日期",
            "endDate": "代理结束日期",
        },
        "Succession": {
            "predecessor": "前身实体 (LegalEntity)",
            "successor": "继承实体 (LegalEntity)",
            "role": "角色",
            "status": "状态",
            "startDate": "继承日期",
        },
        "Occupancy": {
            "holder": "担任职务者 (Person)",
            "post": "职务 (Position)",
            "status": "状态",
            "startDate": "上任日期",
            "endDate": "卸任日期",
            "declarationDate": "资产申报日期",
        },
        "Family": {
            "person": "关系主体 (Person)",
            "relative": "亲属 (Person)",
            "relationship": "亲属关系（从 person 视角，如 mother）",
            "startDate": "关系开始日期",
            "endDate": "关系结束日期",
        },
        "Associate": {
            "person": "关系主体 (Person)",
            "associate": "关联人 (Person)",
            "relationship": "关联性质",
            "startDate": "关系开始日期",
            "endDate": "关系结束日期",
        },
        "Payment": {
            "payer": "付款人 (LegalEntity)",
            "beneficiary": "收款人 (LegalEntity)",
            "amount": "金额",
            "currency": "货币",
            "amountUsd": "美元等值金额",
            "date": "交易日期",
            "startDate": "开始日期",
            "endDate": "结束日期",
        },
        "Debt": {
            "debtor": "债务人 (LegalEntity)",
            "creditor": "债权人 (LegalEntity)",
            "amount": "金额",
            "currency": "货币",
            "amountUsd": "美元等值金额",
            "startDate": "债务开始日期",
            "endDate": "债务到期日期",
        },
        "Documentation": {
            "document": "关联文档 (Document)",
            "entity": "关联实体 (Thing)",
            "role": "角色",
            "status": "状态",
            "startDate": "开始日期",
            "endDate": "结束日期",
        },
    }

    # ------------------------------------------------------------------ #
    # Dictionaries — seed terms for rule-based matching                   #
    # ------------------------------------------------------------------ #
    dictionaries = {
        "sanction_programs": [
            # US
            "OFAC SDN", "OFAC Non-SDN", "OFAC Consolidated", "OFAC CAPTA",
            "OFAC NS-MBS List", "US BIS Entity List", "US AECA Debarred",
            # UN
            "UN Security Council", "UNSCR 1267", "UNSCR 1988", "UNSCR 1718",
            "UN Consolidated List",
            # EU
            "EU Consolidated Sanctions", "EU Restrictive Measures",
            # UK
            "UK OFSI", "UK Sanctions List",
            # Other multilateral / national
            "Australian DFAT", "Canadian SEMA", "Swiss SECO",
            "Japan METI", "INTERPOL Red Notice",
        ],
        "listing_authorities": [
            "OFAC", "US Treasury", "US Department of State",
            "European Commission", "Council of the EU",
            "UK OFSI", "HM Treasury",
            "UN Security Council", "UN 1267 Committee",
            "FATF", "Egmont Group",
            "World Bank Integrity Vice Presidency",
            "Asian Development Bank OAI",
            "美国财政部", "欧盟委员会", "联合国安理会", "英国财政部",
            "中国商务部", "中华人民共和国财政部",
        ],
        "risk_topics": [
            # FtM topic tags used in OpenSanctions
            "sanction", "debarment", "role.pep", "role.rca",
            "crime.terror", "crime.proliferation", "crime.cyber",
            "crime.narcotics", "crime.corruption", "crime.money_laundering",
            "crime.traffick", "export.control", "poi",
        ],
        "legal_suffixes": [
            "Corp", "Corporation", "Inc", "Incorporated", "Ltd", "Limited",
            "LLC", "LLP", "PLC", "GmbH", "S.A.", "B.V.", "AG", "N.V.", "S.E.",
            "JSC", "OJSC", "PJSC", "CJSC",            # Russian/CIS forms
            "有限责任公司", "股份有限公司", "集团", "控股", "投资",
        ],
        "vessel_types": [
            "Bulk Carrier", "Container Ship", "Oil Tanker", "LNG Carrier",
            "General Cargo", "Chemical Tanker", "Crude Oil Tanker",
            "散货船", "集装箱船", "油轮", "液化气船", "杂货船",
        ],
    }

    dictionary_entity_map = {
        "sanction_programs": "Sanction",
        "listing_authorities": "Sanction",
        "risk_topics": "Sanction",
        "legal_suffixes": "Company",
        "vessel_types": "Vessel",
    }

    # ------------------------------------------------------------------ #
    # Patterns — regex for identifiers common in sanctions documents       #
    # ------------------------------------------------------------------ #
    patterns = {
        # US OFAC SDN record ID
        "ofac_id": [
            r"\bOFAC[-\s]?(?:SDN[-\s]?)?\d+\b",
            r"\bSDN[-\s]?\d+\b",
        ],
        # UN Security Council designation number
        "unsc_id": [
            r"\bQDe?\.\d{3,4}(?:\.\d{2})?\b",   # QDe.001 / QDi.123.07
            r"\bTAi?\.\d{3,4}\b",
        ],
        # EU Sanctions identifier
        "eu_id": [
            r"\bEU[-\s]\d{4,10}\b",
        ],
        # ISIN (financial security)
        "isin": [
            r"\b[A-Z]{2}[A-Z0-9]{9}\d\b",
        ],
        # LEI (Legal Entity Identifier — ISO 17442)
        "lei": [
            r"\b[A-Z0-9]{18}\d{2}\b",
        ],
        # IMO vessel number (7 digits with checksum)
        "imo_number": [
            r"\bIMO[\s:]*\d{7}\b",
        ],
        # MMSI (Maritime Mobile Service Identity)
        "mmsi": [
            r"\bMMSI[\s:]*\d{9}\b",
        ],
        # SWIFT/BIC code
        "swift_bic": [
            r"\b[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}(?:[A-Z0-9]{3})?\b",
        ],
        # Passport / travel document number
        "passport_no": [
            r"\b[A-Z]{1,2}\d{6,9}\b",
        ],
        # Cryptocurrency wallet addresses (BTC, ETH)
        "crypto_address": [
            r"\b1[13-9A-HJ-NP-Za-km-z]{25,34}\b",   # BTC P2PKH
            r"\b3[1-9A-HJ-NP-Za-km-z]{25,34}\b",    # BTC P2SH
            r"\bbc1[ac-hj-np-z02-9]{6,87}\b",        # BTC bech32
            r"\b0x[0-9a-fA-F]{40}\b",                # ETH / ERC-20
        ],
        # General date ranges common in sanction records
        "listing_date": [
            r"\b(?:listed|designated|added)\s+(?:on\s+)?(?:\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}|\d{4}-\d{2}-\d{2})\b",
        ],
        # Beneficial ownership percentage
        "ownership_pct": [
            r"\b\d{1,3}(?:\.\d{1,2})?\s*%\s*(?:ownership|stake|interest|shares?|equity|holding)\b",
            r"\b(?:ownership|stake|interest|shares?|equity|holding)\s+of\s+\d{1,3}(?:\.\d{1,2})?\s*%\b",
        ],
        # Unified Social Credit Code (USCC) 中国统一社会信用代码
        "uscc": [
            r"\b[0-9A-HJ-NPQRTUWXY]{2}\d{6}[0-9A-HJ-NPQRTUWXY]{10}\b",
        ],
        # Russian INN (tax ID)
        "inn": [
            r"\b\d{10}\b",   # 10-digit for companies
            r"\b\d{12}\b",   # 12-digit for individuals
        ],
        # FIGI (Financial Instrument Global Identifier)
        "figi": [
            r"\bBBG[A-Z0-9]{9}\b",
        ],
    }

    pattern_entity_map = {
        "ofac_id": "Sanction",
        "unsc_id": "Sanction",
        "eu_id": "Sanction",
        "isin": "Security",
        "lei": "Company",
        "imo_number": "Vessel",
        "mmsi": "Vessel",
        "swift_bic": "Company",
        "passport_no": "Passport",
        "crypto_address": "CryptoWallet",
        "listing_date": "Sanction",
        "ownership_pct": "Ownership",
        "uscc": "Company",
        "inn": "Company",
        "figi": "Security",
    }

    # ------------------------------------------------------------------ #
    # LLM extraction prompt — uses FtM property names                    #
    # ------------------------------------------------------------------ #
    extraction_prompt = """你是一名专业的制裁合规与金融犯罪知识图谱构建助手。请从以下文本中提取实体和关系。

文本内容：
{text}

请严格按照以下JSON格式返回，不要添加任何其他内容：

{{
    "entities": [
        {{
            "name": "实体名称（保留原文语言和官方拼写）",
            "type": "FtM实体类型",
            "properties": {{
                "alias": ["别名1", "别名2"],
                "country": "关联国家代码",
                "topics": ["sanction", "role.pep"],
                "sourceUrl": "信息来源链接"
            }}
        }}
    ],
    "relations": [
        {{
            "from_entity": "源实体名称",
            "to_entity": "目标实体名称",
            "relation_type": "关系类型",
            "properties": {{
                "startDate": "开始日期",
                "endDate": "结束日期",
                "role": "角色/职务（如有）"
            }}
        }}
    ]
}}

实体类型：{entity_types}
关系类型：{relation_types}

提取规则：
1. 【实体类型】严格使用 FtM 实体类型：Person、Company、Organization、PublicBody、Vessel、Airplane、CryptoWallet、Security、Sanction、Address、Position、Ownership、Directorship、Membership、Employment、Representation、Succession、Occupancy、Family、Associate、Payment、Debt、Identification、Passport。
2. 【名称处理】保留原文官方名称、所有 alias 和 previousName，包括西里尔字母、阿拉伯字母等非拉丁文字。
3. 【标识符提取】精确提取并放入对应 FtM 属性字段：
   - 制裁标识：Sanction.authorityId（OFAC ID）、Sanction.unscId（QDe/QDi/TAi）
   - 公司标识：Company.leiCode（LEI）、Company.registrationNumber、Company.uscCode（USCC）、Company.innCode（INN）、Company.swiftBic（SWIFT/BIC）
   - 证券标识：Security.isin（ISIN）、Security.figiCode（FIGI）、Security.ticker
   - 船舶标识：Vessel.imoNumber（IMO）、Vessel.mmsi（MMSI）、Vessel.callSign
   - 个人标识：Person.passportNumber、Person.idNumber、Person.taxNumber
   - 加密货币：CryptoWallet.publicKey
   - 护照/证件：Passport.number、Identification.number
4. 【制裁信息】Sanction 实体需记录：authority（制裁机构）、program（制裁项目）、authorityId/unscId（编号）、provisions（制裁措施）、reason（原因）、listingDate/startDate/endDate（日期范围）、status（状态）。
5. 【关系穿透】受益所有权链用 Ownership 实体记录（owner → asset），标注 percentage/sharesCount；董事关系用 Directorship（director → organization）；家庭亲属用 Family（person → relative，标注 relationship 如 mother/father/spouse）；关联人用 Associate。
6. 【PEP 信息】政治公众人物：提取 Position 实体（职务名称 + 所属 organization），Occupancy 实体记录 holder（Person）→ post（Position）的时间段。
7. 【金融流动】Payment 实体记录 payer → beneficiary，标注 amount/currency/date；Debt 实体记录 debtor → creditor。
8. 【船只/飞机】Vessel 记录 flag/imoNumber/type/tonnage；Airplane 记录 serialNumber/registrationNumber/type。
9. 【地址】Address 实体使用 full/street/city/state/postalCode/country 字段；其他实体通过 located_at 关系关联。
10. 【properties 字段】使用 FtM 标准属性名（见 entity_properties 定义），不要自行编造字段名。
11. 【不确定信息】置信度低的在 properties 中标注 "confidence": "low" 或 "source": "inferred"。
12. 仅提取文本中明确出现或可直接推断的信息，不要凭借背景知识补全未提及的事实。
"""
