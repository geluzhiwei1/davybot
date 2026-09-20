# CubeSandbox 自定义模板 — 基于 sandbox-code 预装 dawei agent 常用库
# Build: docker build -t localhost:5000/dawei-sandbox:latest .
# Then: cubemastercli tpl create-from-image --image localhost:5000/dawei-sandbox:latest ...

FROM cube-sandbox-cn.tencentcloudcr.com/cube-sandbox/sandbox-code:latest

# 预装 dawei agent 工具执行所需的常用库 (来自 agent/pyproject.toml dependencies)
# 分层安装: 文档处理 → 数据科学 → HTTP/工具 → 系统工具

# ── 系统依赖 ──
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    wget \
    git \
    zip \
    unzip \
    fontconfig \
    fonts-liberation \
    fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

# ── Python 文档处理库 (agent/pyproject.toml) ──
RUN pip install --no-cache-dir \
    python-docx \
    openpyxl \
    reportlab \
    PyMuPDF \
    pypdfium2 \
    markitdown

# ── Python 数据科学库 ──
RUN pip install --no-cache-dir \
    numpy \
    pandas \
    matplotlib \
    seaborn \
    scipy \
    scikit-learn

# ── Python HTTP / 工具库 (agent/pyproject.toml) ──
RUN pip install --no-cache-dir \
    requests \
    httpx \
    aiohttp \
    PyYAML \
    jinja2 \
    jsonschema \
    python-dotenv \
    python-frontmatter \
    aiosqlite \
    beautifulsoup4 \
    lxml \
    Pillow

# ── 验证安装 ──
RUN python3 -c "\
import docx, openpyxl, reportlab, fitz, pypdfium2; print('doc libs OK'); \
import numpy, pandas, matplotlib, scipy, sklearn; print('science libs OK'); \
import requests, httpx, aiohttp, yaml, jinja2, jsonschema; print('http/util libs OK'); \
import bs4, lxml, PIL; print('scrape/image libs OK'); \
print('ALL LIBRARIES INSTALLED SUCCESSFULLY') \
"
