# 使用技能 - 用户指南

## 简介

**技能(Skills)** 是 Dawei 分享专业知识和最佳实践的方式。可以将它们视为"操作指南"，帮助 AI 助手更有效地完成专业任务。

当你给 Dawei 分配任务时，它可以参考相关技能，确保遵循经过验证的工作流程和行业最佳实践。

### 技能解决什么问题？

- **不一致性**：每次执行相同任务时采用不同的方法
- **重复解释**：反复说明你希望如何完成工作
- **最佳实践**：确保代理使用经过验证的方法
- **复杂工作流**：需要特定专业知识的多步骤流程

## 理解技能

### 技能结构

一个技能包含：

```
my-skill/
├── SKILL.md              # 主要说明（必需）
├── template.py           # 示例模板（可选）
├── config.json           # 参考配置（可选）
└── README.md             # 额外文档（可选）
```

### 技能里有什么？

打开任何 `SKILL.md`，你会发现：

```markdown
---
name: pdf
description: PDF 处理、OCR 和提取工作流
---

# PDF 处理技能

本技能指导你如何处理 PDF 文件...

## 常见工作流

### 从 PDF 提取文本
1. 使用 pdf_extractor 工具...
2. 对于扫描的 PDF，首先应用 OCR...

### 提取表格
1. 将 PDF 转换为图片...
2. 使用带表格检测的 OCR...
```

## 发现已有技能

### 通过 CLI

列出所有可用技能：

```bash
# 查看所有技能
dawei skills list

# 搜索特定技能
dawei skills search pdf
dawei skills search "表格提取"
dawei skills search web
```

### 通过 TUI

在 TUI（文本用户界面）中，使用 `@skill:` 语法：

```
# 输入请求时
用户: @skill:pdf 如何从扫描的 PDF 中提取表格？
```

TUI 会：
1. 显示与查询匹配的可用技能
2. 输入 `@skill:` 时自动建议技能名称
3. 显示技能描述供预览

### 通过 Web UI

通过 Web 界面访问技能：
- 导航到 **技能** 部分
- 浏览所有可用技能
- 按关键词搜索
- 查看技能详细信息和资源

## 使用技能

### 隐式使用（推荐）

只需自然地描述你的任务 - Dawei 会自动找到相关技能：

```
用户: 从这个扫描的 PDF 文档中提取表格

# Dawei 自动执行：
# 1. 搜索相关技能（找到 "pdf" 技能）
# 2. 加载技能说明
# 3. 遵循推荐的表格提取工作流
# 4. 使用适当的工具（pdf2image、OCR、表格提取）
```

### 显式使用

直接请求特定技能：

```
用户: @skill:pdf 帮我处理这个发票 PDF

# Dawei 将：
# 1. 加载 pdf 技能
# 2. 应用 PDF 特定的工作流
# 3. 使用推荐的工具和设置
```

### 实用示例

#### 示例 1：PDF 处理

```
用户: 我有一个扫描的合同 PDF，需要提取所有文本

# Dawei 的操作（使用 pdf 技能）：
# 1. 识别这是 PDF 任务
# 2. 加载 pdf 技能
# 3. 遵循扫描 PDF 的 OCR 工作流
# 4. 使用 pdf2image + pytesseract
# 5. 返回提取的文本及置信度分数
```

#### 示例 2：Excel 处理

```
用户: 总结这个 Excel 文件中的销售数据

# Dawei 的操作（使用 xlsx 技能）：
# 1. 加载 xlsx 技能
# 2. 读取 Excel 文件结构
# 3. 识别数据模式
# 4. 创建汇总统计
# 5. 遵循 xlsx 最佳实践生成见解
```

#### 示例 3：Web 开发

```
用户: @skill:frontend-design 创建一个响应式仪表板布局

# Dawei 的操作（使用 frontend-design 技能）：
# 1. 加载前端设计技能
# 2. 遵循响应式设计原则
# 3. 使用推荐的 CSS 框架
# 4. 实现可访问性最佳实践
# 5. 生成整洁、可维护的代码
```

## 创建自定义技能

### 何时创建自定义技能

当你遇到以下情况时创建技能：
- 对任务完成方式有特定偏好
- 经常在专业领域工作
- 想要记录团队最佳实践
- 有经常重复的复杂工作流

### 分步指南：创建你的第一个技能

#### 步骤 1：创建技能目录

技能位于工作空间的 `.dawei/skills/` 下：

```bash
# 导航到工作空间
cd my-workspace

# 创建新技能目录
mkdir -p .dawei/skills/my-custom-skill
cd .dawei/skills/my-custom-skill
```

#### 步骤 2：编写 SKILL.md

创建主技能文件：

```markdown
---
name: my-custom-skill
description: 针对我特定需求的自定义工作流
version: 1.0.0
author: 你的名字
---

# 我的自定义技能

## 用途
本技能通过遵循[你的方法]来帮助完成[特定任务]。

## 前置条件
- 已安装工具 A
- 已设置配置 B

## 工作流

### 步骤 1：准备
始终从以下开始...
- 检查 X
- 验证 Y

### 步骤 2：执行
遵循以下步骤：
1. 首先，执行此操作...
2. 然后，执行彼操作...
3. 最后，验证 Z

### 步骤 3：验证
确保结果满足以下标准：
- 标准 1
- 标准 2

## 常见模式

### 模式 1：[名称]
当[情况]时，使用此方法：
\`\`\`python
# 示例代码
result = do_something()
\`\`\`

### 模式 2：[名称]
对于[不同情况]，执行：
\`\`\`python
# 替代方法
result = do_something_else()
\`\`\`

## 故障排除

### 问题：[问题]
**解决方案**：[修复方法]

### 问题：[另一个问题]
**解决方案**：[其他修复方法]

## 资源
- 外部文档链接
- 参考资料
```

#### 步骤 3：添加可选资源

在同一目录中包含有用的文件：

```bash
# 添加模板
cat > template.py << 'EOF'
def example_function():
    """模板函数"""
    pass
EOF

# 添加配置示例
cat > config.example.json << 'EOF'
{
    "setting1": "value1",
    "setting2": "value2"
}
EOF
```

#### 步骤 4：测试你的技能

```bash
# 验证 Dawei 可以找到它
dawei skills list | grep my-custom-skill

# 测试使用它
dawei agent run ./my-workspace "@skill:my-custom-skill 帮我..."
```

### 真实技能示例

#### 示例：Git 工作流技能

```markdown
---
name: git-workflow
description: 我们团队的 Git 分支和提交约定
version: 1.0.0
---

# 团队 Git 工作流

## 分支命名
- 功能分支：`feature/ISSUE-DESCRIPTION`
- 错误修复分支：`bugfix/ISSUE-DESCRIPTION`
- 热修复分支：`hotfix/VERSION-DESCRIPTION`

## 提交信息
格式：`ISSUE: 简要描述`

示例：`DAWEI-123: 添加用户认证`

## 工作流
1. 从 main 创建功能分支
2. 使用正确信息进行提交
3. 推送到远程
4. 使用模板创建 PR
5. 请求审查
6. 处理反馈
7. 批准后合并

## PR 模板
\`\`\`
## 摘要
- [ ] 变更 1
- [ ] 变更 2

## 测试
- [ ] 单元测试通过
- [ ] 手动测试完成
\`\`\`
```

#### 示例：代码审查技能

```markdown
---
name: code-review
description: 代码审查指南和检查清单
version: 1.0.0
---

# 代码审查指南

## 检查清单
- [ ] 代码遵循项目风格指南
- [ ] 没有硬编码的密钥
- [ ] 实现了错误处理
- [ ] 添加/更新了测试
- [ ] 更新了文档
- [ ] 没有明显的性能问题
- [ ] 检查了安全漏洞

## 检查要点

### 安全性
- SQL 注入漏洞
- XSS 向量
- 认证/授权问题
- 日志中的敏感数据

### 性能
- N+1 查询问题
- 缺少索引
- 不必要的循环
- 内存泄漏

### 可维护性
- 清晰的变量名
- 适当的注释
- 函数长度 < 50 行
- 遵循 DRY 原则
```

## 技能管理

### 查看技能

```bash
# 列出所有技能
dawei skills list

# 查看技能详情
dawei skills get pdf

# 查看技能内容
dawei skills content pdf
```

### 更新技能

直接编辑 `SKILL.md` 文件：

```bash
# 工作空间技能（可编辑）
vim .dawei/skills/my-skill/SKILL.md

# 更改立即生效
```

### 删除技能

```bash
# 删除工作空间技能
rm -rf .dawei/skills/my-skill

# 注意：系统技能无法删除
```

## 组织技能

### 按领域

```
.dawei/skills/
├── development/
│   ├── python/
│   ├── javascript/
│   └── testing/
├── data/
│   ├── analysis/
│   └── visualization/
└── ops/
    ├── deployment/
    └── monitoring/
```

### 按工作流

```
.dawei/skills/
├── data-processing/
├── report-generation/
├── code-review/
└── deployment/
```

### 按项目

```
.dawei/skills/
├── project-alpha/
├── project-beta/
└── common/
```

## 技能模式

技能可以针对特定模式以适应不同上下文：

```bash
# 通用技能（始终可用）
.dawei/skills/
└── common/

# Web 开发模式
.dawei/skills-web/
└── frontend/

# 数据分析模式
.dawei/skills-data/
└── visualization/
```

当设置工作空间模式时，Dawei 会优先考虑特定模式的技能：

```bash
# 设置工作空间模式
dawei workspace set-mode web

# 现在特定于 Web 的技能被优先考虑
```

## 最佳实践

### 编写好技能

1. **具体明确**：清晰、可操作的说明
2. **提供示例**：展示，而不只是讲述
3. **包含边界情况**：出错时该怎么做
4. **保持更新**：定期审查和修改
5. **版本控制**：跟踪技能的变更

### 技能设计原则

1. **单一用途**：每个技能应专注于一个领域
2. **渐进式**：从简单开始，逐步添加细节
3. **可测试**：技能应产生一致的结果
4. **可维护**：易于更新和改进

### 应避免的常见错误

- ❌ 太过通用的技能
- ❌ 缺少边界情况
- ❌ 过时的信息
- ❌ 不清楚的工作流
- ❌ 缺少示例

## 高级用法

### 技能组合

技能可以引用其他技能：

```markdown
## 工作流
1. 首先，应用 @skill:setup-environment
2. 然后，使用 @skill:build-process
3. 最后，运行 @skill:deploy-checklist
```

### 条件逻辑

使用条件指导代理：

```markdown
## 方法选择

如果文件大于 100MB：
- 使用流式方法
- 分块处理

如果文件较小：
- 完整加载到内存
- 一次性处理
```

### 资源文件

为代理包含模板：

```markdown
## 模板

使用 template.py 中的模板作为起点。

代理可以通过以下方式访问它：
```
read_skill_resource(skill_name="my-skill", resource="template.py")
```
```

## 故障排除

### 找不到技能

**问题**：Dawei 看不到你的技能

**解决方案**：
1. 检查目录结构：`.dawei/skills/your-skill/SKILL.md`
2. 验证 frontmatter 包含 `name` 字段
3. 确保 `name` 与目录名匹配
4. 运行 `dawei skills list` 验证

### 加载了错误的技能

**问题**：低优先级技能覆盖了高优先级技能

**解决方案**：
1. 检查技能位置（工作空间 > 系统 > 用户）
2. 验证特定模式技能与通用技能
3. 删除重复的技能名称

### 技能未应用

**问题**：Dawei 没有遵循你的技能

**解决方案**：
1. 使任务描述更加明确
2. 使用 `@skill:name` 强制使用特定技能
3. 检查技能说明是否清晰
4. 验证技能与任务相关

## 技巧与窍门

### 快速发现技能

```bash
# 查找与主题相关的技能
dawei skills search "data"

# 查看技能有什么资源
dawei skills resources pdf

# 预览技能内容
dawei skills content pdf | head -50
```

### 技能版本控制

在 frontmatter 中跟踪版本：

```markdown
---
version: 2.1.0
changelog:
  - 2.1.0: 添加了 OCR 工作流
  - 2.0.0: 重大重构
  - 1.0.0: 初始发布
---
```

### 团队协作

通过版本控制共享技能：

```bash
# 将技能提交到 git
git add .dawei/skills/
git commit -m "添加数据处理技能"

# 团队成员可以拉取更新
git pull
```

## 总结

- **技能** 是指导 Dawei 行为的专业知识
- **发现** 技能使用 `@skill:` 语法或自然语言
- **创建** 针对你特定工作流的自定义技能
- **组织** 按领域、项目或工作流组织技能
- **维护** 技能作为随需求发展的动态文档

技能是让 Dawei 对你的特定用例更有效地的强大方式。从内置技能开始，然后在工作中发现模式时创建自己的技能。
