# TUI Internationalization (i18n)

## 快速开始

### 1. 导入翻译函数

```python
from dawei.tui.i18n import _, set_language
```

### 2. 使用翻译

```python
# 基础翻译
text = _("Hello, World!")

# 复数翻译
files_text = _n("One file", "Multiple files", count)
```

### 3. 切换语言

```python
# 切换到简体中文
set_language("zh_CN")

# 切换到繁體中文
set_language("zh_TW")

# 切换到英文
set_language("en")
```

## 支持的语言

- `en` - English
- `zh_CN` - 简体中文
- `zh_TW` - 繁體中文

## 文件结构

```
locales/
├── en/LC_MESSAGES/dawei_tui.po    # 英文翻译
├── zh_CN/LC_MESSAGES/dawei_tui.po # 简体中文
└── zh_TW/LC_MESSAGES/dawei_tui.po # 繁体中文
```

## 测试

```bash
cd agent
python3 dawei/tui/test_i18n.py
```

## 编译翻译（可选）

虽然系统可以直接读取 .po 文件，但如果需要 .mo 文件：

```bash
python3 dawei/tui/compile_translations.py
```

## 详细文档

查看完整文档：
- [使用指南](../../../docs/features/tui-i18n-guide.md)
- [实施总结](../../../docs/features/tui-i18n-summary.md)

## API 参考

### 函数

- `_(message: str) -> str` - 翻译消息
- `_n(singular: str, plural: str, count: int) -> str` - 复数翻译
- `set_language(language: str) -> None` - 设置语言
- `get_current_language() -> str` - 获取当前语言
- `get_system_language() -> str` - 检测系统语言
- `get_supported_languages() -> Dict[str, str]` - 获取支持的语言列表

## 示例

```python
from dawei.tui.i18n import _, _n, set_language, get_system_language

# 自动检测系统语言
system_lang = get_system_language()
set_language(system_lang)

# 使用翻译
title = _("Dawei TUI")
button_text = _("Quit")
status = _("Ready")

# 复数形式
count = 5
files_msg = _n("One file", "Multiple files", count)
```
