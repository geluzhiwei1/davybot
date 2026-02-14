# Dawei CLI - 命令行工具

## 快速开始

```bash
# 安装依赖
cd services/agent-api
uv pip install fire

# 运行示例
python3 -m dawei.cli run ./my-workspace openai/gpt-4 code "创建一个hello world程序"

# 查看帮助
python3 -m dawei.cli help
```

## 功能特性

✅ **直接调用**：绕过HTTP/WebSocket，直接使用Agent API
✅ **参数化**：灵活配置workspace、LLM、mode、message
✅ **非交互式**：完全自动化执行，无需用户干预
✅ **Fire库**：使用Python Fire提供友好的CLI接口
✅ **超时控制**：可配置执行超时时间
✅ **详细日志**：可选的verbose模式查看详细执行过程

## 命令格式

```bash
python3 -m dawei.cli run <workspace> <llm> <mode> <message> [options]
```

### 参数

- `workspace` - 工作区路径
- `llm` - LLM模型名称（如 openai/gpt-4, deepseek/deepseek-chat）
- `mode` - Agent模式（code, ask, architect, plan, debug）
- `message` - 用户消息或指令

### 可选参数

- `--verbose` - 启用详细日志
- `--timeout` - 超时时间（秒），默认1800

## 使用示例

### 代码生成

```bash
python3 -m dawei.cli run ./my-workspace openai/gpt-4 code "创建一个快速排序算法"
```

### 问答

```bash
python3 -m dawei.cli run ./my-workspace deepseek/deepseek-chat ask "什么是专利？"
```

### 架构设计

```bash
python3 -m dawei.cli run ./my-workspace openai/gpt-4 architect "设计一个RESTful API"
```

### 启用详细日志

```bash
python3 -m dawei.cli run ./my-workspace openai/gpt-4 code "创建hello world" --verbose
```

## 项目结构

```
dawei/cli/
  ├── __init__.py       # 模块初始化
  ├── __main__.py       # 入口点（支持 python -m dawei.cli）
  ├── config.py         # 配置管理和验证
  ├── runner.py         # Agent执行封装器
  ├── agent_cli.py      # Fire命令行接口
  └── README.md         # 本文档
```

## 实现细节

### 配置管理 (config.py)

- `CLIConfig` 类：管理所有CLI配置
- 参数验证：workspace路径、mode有效性、message非空
- 环境变量加载：自动从.env文件加载
- 工作区初始化：自动创建.dawei目录结构

### Agent执行器 (runner.py)

- `AgentRunner` 类：封装Agent执行流程
- 异步执行：完整支持asyncio
- 超时控制：使用asyncio.timeout
- 资源清理：确保正确清理workspace和agent

### Fire接口 (agent_cli.py)

- `CLIMain` 类：暴露给Fire的命令接口
- 友好的命令名称：run, version, help
- 结果格式化：清晰的执行结果展示
- 错误处理：捕获并显示所有错误

### 模块入口 (__main__.py)

- 支持 `python -m dawei.cli` 调用
- 简单的入口点，调用agent_cli的main函数

## 依赖

- Python 3.12+
- fire 0.7.0+
- 其他项目依赖（见 pyproject.toml）

## 环境配置

### 必需环境变量

```bash
# LLM API 密钥（至少配置一个）
LITELLM_API_KEY=your_api_key
OPENAI_API_KEY=your_openai_key
```

### 可选环境变量

```bash
# 日志级别
LOG_LEVEL=INFO

# 工作区配置
WORKSPACES_ROOT=./workspaces
```

## 文档

- [详细使用文档](../../../docs/user/CLI.md)
- [示例脚本](../../examples/cli_examples.sh)
- [项目主文档](../../../CLAUDE.md)

## 开发

### 测试

```bash
# 测试help命令
python3 -m dawei.cli help

# 测试version命令
python3 -m dawei.cli version

# 测试简单执行（需要API密钥）
python3 -m dawei.cli run /tmp/test-workspace ollama/llama2 ask "1+1等于几？"
```

### 添加新命令

在 `agent_cli.py` 的 `CLIMain` 类中添加新方法：

```python
def new_command(self, arg1, arg2):
    """新命令的描述"""
    # 实现逻辑
    pass
```

## 故障排除

### 常见错误

1. **ModuleNotFoundError: No module named 'fire'**
   ```bash
   uv pip install fire
   ```

2. **No LLM API key found**
   - 检查 .env 文件是否存在
   - 确保 LITELLM_API_KEY 或 OPENAI_API_KEY 已设置

3. **Workspace path does not exist**
   - 确保workspace路径存在
   - CLI会自动创建.dawei目录结构

4. **Invalid mode**
   - 检查mode是否为: code, ask, architect, plan, debug

## 贡献

欢迎提交问题和拉取请求！

## 许可

与主项目相同的许可。
