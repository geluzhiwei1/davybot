# Dawei 架构图文档

## 1. 系统架构图（分层架构）

```mermaid
graph TB
    subgraph "UI Layer - 用户界面层"
        CLI[CLI<br/>dawei命令]
        TUI[TUI<br/>文本界面]
        REST[REST API<br/>FastAPI]
        WebUI[WUI <br/>Web图形界面]
    end

    subgraph "Communication Layer - 通信层"
        WS[WebSocket<br/>实时通信]
        Async[AsyncTask<br/>异步任务]
        A2UI[A2UI<br/>交互式UI]
    end

    subgraph "Agent Layer - 智能体层"
        Agent[Agent<br/>核心智能体]
        TaskEngine[TaskGraph<br/>任务图引擎]
        Mode[Mode System<br/>PDCA模式]
        Memory[Memory<br/>记忆系统]
    end

    subgraph "Tool Layer - 工具层"
        ToolMgr[ToolManager<br/>工具管理]
        Skill[SkillManager<br/>技能管理]
        Sandbox[Sandbox<br/>沙箱执行]
        MCP[MCP Manager<br/>MCP工具]
    end

    subgraph "LLM Layer - 大模型层"
        LLMProvider[LLMProvider<br/>多提供商]
        ModelRouter[ModelRouter<br/>模型路由]
        Circuit[CircuitBreaker<br/>熔断器]
        Queue[RequestQueue<br/>请求队列]
    end

    subgraph "Data Layer - 数据层"
        Storage[Storage<br/>存储抽象]
        Workspace[Workspace<br/>工作空间]
        Conversation[Conversation<br/>会话管理]
        Checkpoint[Checkpoint<br/>检查点]
    end

    subgraph "Infrastructure Layer - 基础设施层"
        EventBus[EventBus<br/>事件总线]
        DI[DI Container<br/>依赖注入]
        Config[Config<br/>配置管理]
        Logger[Logger<br/>日志系统]
        Metrics[Metrics<br/>指标收集]
    end

    %% 连接关系
    CLI --> Agent
    TUI --> Agent
    REST --> WS

    WS --> Agent
    Async --> Agent
    A2UI --> Agent

    Agent --> TaskEngine
    Agent --> Mode
    Agent --> Memory

    TaskEngine --> ToolMgr
    TaskEngine --> LLMProvider

    ToolMgr --> Skill
    ToolMgr --> Sandbox
    ToolMgr --> MCP

    LLMProvider --> ModelRouter
    ModelRouter --> Circuit
    Circuit --> Queue

    Agent --> Storage
    Agent --> Workspace
    Agent --> Conversation
    TaskEngine --> Checkpoint

    Agent --> EventBus
    Agent --> DI
    Agent --> Config
    Agent --> Logger
    Agent --> Metrics

    style Agent fill:#ff6b6b,stroke:#c92a2a,stroke-width:3px
    style EventBus fill:#ffd43b,stroke:#fab005,stroke-width:2px
    style DI fill:#ffd43b,stroke:#fab005,stroke-width:2px
```

## 2. 3C 图（Component - Class - Connection）

### 2.1 核心 3C 图

```mermaid
graph LR
    subgraph "Component: Agent Orchestration"
        direction TB
        A1[Class: Agent<br/>agentic/agent.py]
        A2[Class: TaskGraphExecutionEngine<br/>agentic/task_graph_excutor.py]
        A3[Class: TaskNodeExecutionEngine<br/>agentic/task_node_executor.py]
        A4[Class: CheckpointManager<br/>agentic/checkpoint_manager.py]
        A5[Class: ContextManager<br/>agentic/context_manager.py]

        A1 --"owns"--> A2
        A1 --"creates"--> A3
        A1 --"uses"--> A4
        A1 --"uses"--> A5
        A2 --"manages"--> A3
    end

    subgraph "Component: Tool System"
        direction TB
        T1[Class: ToolManager<br/>tools/tool_manager.py]
        T2[Class: ToolExecutor<br/>tools/tool_executor.py]
        T3[Class: SkillManager<br/>tools/skill_manager.py]
        T4[Class: CustomBaseTool<br/>tools/custom_base_tool.py]

        T1 --"provides tools to"--> T2
        T2 --"executes"--> T4
        T1 --"manages"--> T3
    end

    subgraph "Component: LLM Integration"
        direction TB
        L1[Class: LLMProvider<br/>llm_api/llm_provider.py]
        L2[Class: ModelRouter<br/>llm_api/model_router.py]
        L3[Class: CircuitBreaker<br/>llm_api/circuit_breaker.py]
        L4[Class: RateLimiter<br/>llm_api/rate_limiter.py]

        L1 --"uses"--> L2
        L2 --"protected by"--> L3
        L3 --"limited by"--> L4
    end

    subgraph "Component: Communication"
        direction TB
        C1[Class: WebSocketManager<br/>websocket/manager.py]
        C2[Class: MessageRouter<br/>websocket/router.py]
        C3[Class: SessionManager<br/>websocket/session.py]
        C4[Protocol: MessageProtocol<br/>websocket/protocol.py]

        C1 --"routes via"--> C2
        C1 --"manages"--> C3
        C2 --"validates"--> C4
    end

    subgraph "Component: Infrastructure"
        direction TB
        I1[Class: EventBus<br/>core/events.py]
        I2[Class: DependencyContainer<br/>core/dependency_container.py]
        I3[Class: Settings<br/>config/settings.py]
        I4[Class: ErrorHandler<br/>core/error_handler.py]

        I1 --"injected via"--> I2
        I2 --"configured by"--> I3
        I1 --"handled by"--> I4
    end

    %% 组件间连接
    A1 --"sends events to"--> I1
    A1 --"requires tools from"--> T1
    A1 --"requests LLM from"--> L1
    A1 --"communicates via"--> C1

    C1 --"forwards events to"--> I1
    T2 --"emits events to"--> I1
```

### 2.2 详细类关系图

```mermaid
classDiagram
    class Agent {
        -event_bus: EventBus
        -task_engine: TaskGraphExecutionEngine
        -tool_executor: IToolExecutor
        -llm_service: ILLMService
        -mode_manager: ModeManager
        +run(task_graph)
        +stop()
        +switch_mode(mode)
    }

    class TaskGraphExecutionEngine {
        -agent: Agent
        -node_executors: Dict
        +execute(graph)
        +create_node_executor(node)
    }

    class TaskNodeExecutionEngine {
        -node: TaskNode
        -llm_service: ILLMService
        -tool_executor: IToolExecutor
        +execute(node)
        +handle_tool_call(tool)
    }

    class ToolManager {
        -tool_providers: List
        -skill_manager: SkillManager
        +get_tool(name)
        +list_tools()
        +reload_tools()
    }

    class ToolExecutor {
        -tool_manager: ToolManager
        +execute(tool_name, args)
        +execute_tool_call(tool_call)
    }

    class LLMProvider {
        -model_router: ModelRouter
        -circuit_breaker: CircuitBreaker
        -rate_limiter: RateLimiter
        +chat(messages)
        +stream(messages)
    }

    class ModelRouter {
        -models: List
        -load_balancer: LoadBalancer
        +route(request)
        +add_model(model)
    }

    class WebSocketManager {
        -router: MessageRouter
        -sessions: Dict
        -event_bus: EventBus
        +connect(ws)
        +disconnect(session_id)
        +broadcast(message)
    }

    class MessageRouter {
        -handlers: Dict
        +register(message_type, handler)
        +route(message)
    }

    class EventBus {
        -subscribers: Dict
        +subscribe(event_type, handler)
        +publish(event)
    }

    class DependencyContainer {
        -services: Dict
        +register(service, instance)
        +resolve(service_type)
    }

    Agent --> TaskGraphExecutionEngine : owns
    Agent --> IToolExecutor : uses
    Agent --> ILLMService : uses
    Agent --> EventBus : publishes events

    TaskGraphExecutionEngine --> TaskNodeExecutionEngine : creates
    TaskNodeExecutionEngine --> IToolExecutor : uses
    TaskNodeExecutionEngine --> ILLMService : uses

    IToolExecutor --> ToolManager : gets tools
    ToolManager --> SkillManager : manages skills

    ILLMService --> LLMProvider : implementation
    LLMProvider --> ModelRouter : routes to
    ModelRouter --> CircuitBreaker : protected by

    WebSocketManager --> MessageRouter : uses
    MessageRouter --> EventBus : forwards events
    EventBus --> DependencyContainer : injected via
```

## 3. 模块依赖关系图

```mermaid
graph TD
    subgraph "Layer 7: UI Layer"
        CLI[cli/]
        TUI[tui/]
        API[api/]
    end

    subgraph "Layer 6: Communication"
        WebSocket[websocket/]
        AsyncTask[async_task/]
        A2UI[a2ui/]
    end

    subgraph "Layer 5: Agent"
        Agentic[agentic/]
        TaskGraph[task_graph/]
        Mode[mode/]
        Memory[memory/]
    end

    subgraph "Layer 4: Capabilities"
        Tools[tools/]
        Sandbox[sandbox/]
        Skills[skills/]
    end

    subgraph "Layer 3: LLM & Prompts"
        LLMApi[llm_api/]
        Prompts[prompts/]
    end

    subgraph "Layer 2: Data & Storage"
        Storage[storage/]
        Workspace[workspace/]
        Conversation[conversation/]
    end

    subgraph "Layer 1: Infrastructure"
        Core[core/]
        Interfaces[interfaces/]
        Config[config/]
        Entity[entity/]
        Logg[logg/]
    end

    CLI --> Agentic
    TUI --> Agentic
    API --> WebSocket

    WebSocket --> Agentic
    AsyncTask --> Agentic
    A2UI --> Agentic

    Agentic --> TaskGraph
    Agentic --> Mode
    Agentic --> Memory
    Agentic --> Tools
    Agentic --> LLMApi

    TaskGraph --> Tools
    TaskGraph --> LLMApi
    Tools --> Sandbox
    Tools --> Skills

    LLMApi --> Prompts

    Agentic --> Storage
    Agentic --> Workspace
    Agentic --> Conversation

    TaskGraph --> Storage
    Tools --> Workspace

    WebSocket --> Core
    Agentic --> Core
    Tools --> Core

    API --> Entity
    WebSocket --> Entity
    Agentic --> Entity

    Agentic --> Interfaces
    Tools --> Interfaces
    LLMApi --> Interfaces

    Agentic --> Config
    WebSocket --> Config
    API --> Config

    Agentic --> Logg
    WebSocket --> Logg
```

## 4. 核心流程图

### 4.1 Agent 执行流程

```mermaid
sequenceDiagram
    participant User as 用户
    participant WS as WebSocketManager
    participant Agent as Agent
    participant TaskEngine as TaskGraphExecutionEngine
    participant NodeExecutor as TaskNodeExecutionEngine
    participant LLM as LLMProvider
    participant Tools as ToolExecutor
    participant EventBus as EventBus

    User->>WS: 发送消息
    WS->>Agent: 创建/获取 Agent 实例
    Agent->>EventBus: 发布 AGENT_START 事件

    Agent->>TaskEngine: 执行任务图
    TaskEngine->>NodeExecutor: 执行任务节点

    NodeExecutor->>LLM: 请求 LLM 响应
    LLM-->>NodeExecutor: 返回响应（可能包含工具调用）

    alt 需要工具调用
        NodeExecutor->>Tools: 执行工具
        Tools->>EventBus: 发布 TOOL_START 事件
        Tools-->>NodeExecutor: 返回工具结果
        Tools->>EventBus: 发布 TOOL_COMPLETE 事件

        NodeExecutor->>LLM: 继续请求（包含工具结果）
        LLM-->>NodeExecutor: 返回最终响应
    end

    NodeExecutor-->>TaskEngine: 节点完成
    TaskEngine-->>Agent: 任务图完成
    Agent->>EventBus: 发布 AGENT_COMPLETE 事件

    Agent-->>WS: 流式响应
    WS-->>User: 接收结果
```

### 4.2 WebSocket 消息流

```mermaid
sequenceDiagram
    participant Client as 客户端
    participant WS as WebSocketManager
    participant Router as MessageRouter
    participant Handler as ChatHandler
    participant Agent as Agent
    participant EventBus as EventBus

    Client->>WS: WebSocket 连接
    WS->>WS: 创建会话
    WS-->>Client: 发送 CONNECTED 消息

    Client->>WS: USER_MESSAGE
    WS->>Router: 路由消息
    Router->>Handler: ChatHandler 处理

    Handler->>Agent: 提交任务
    Handler->>EventBus: 订阅事件

    Agent->>EventBus: 发布 AGENT_START
    EventBus-->>Handler: 接收事件
    Handler-->>WS: TASK_NODE_START

    Agent->>EventBus: 发布 STREAM_CONTENT
    EventBus-->>Handler: 接收事件
    Handler-->>WS: STREAM_CONTENT
    WS-->>Client: 实时内容流

    Agent->>EventBus: 发布 AGENT_COMPLETE
    EventBus-->>Handler: 接收事件
    Handler-->>WS: AGENT_COMPLETE
    WS-->>Client: 任务完成
```

### 4.3 工具发现和执行流程

```mermaid
sequenceDiagram
    participant Agent as Agent
    participant ToolMgr as ToolManager
    participant Provider as ToolProvider
    participant Tool as CustomTool
    participant Sandbox as Sandbox
    participant EventBus as EventBus

    Agent->>ToolMgr: 请求工具
    ToolMgr->>ToolMgr: 4层配置加载<br/>builtin→system→user→workspace

    ToolMgr->>Provider: 获取工具提供者
    Provider-->>ToolMgr: 返回工具列表

    ToolMgr-->>Agent: 返回可用工具

    Agent->>ToolMgr: 执行工具(tool_name, args)
    ToolMgr->>Tool: 创建工具实例
    Tool->>Sandbox: 验证和准备执行环境
    Sandbox->>Tool: 执行工具

    Tool->>EventBus: 发布 TOOL_START
    Tool->>Tool: 执行实际逻辑
    Tool->>EventBus: 发布 TOOL_COMPLETE

    Tool-->>Sandbox: 返回结果
    Sandbox-->>ToolMgr: 返回结果
    ToolMgr-->>Agent: 返回工具结果
```

## 5. 模式系统（PDCA）图

```mermaid
graph TB
    subgraph "PDCA Cycle"
        Orchestrator[Orchestrator<br/>优先级: 90<br/>🪃]
        Plan[Plan<br/>优先级: 80<br/>📋]
        Do[Do<br/>优先级: 70<br/>⚙️]
        Check[Check<br/>优先级: 75<br/>✓]
        Act[Act<br/>优先级: 78<br/>🚀]
    end

    subgraph "Tool Groups"
        Read[read<br/>文件读取]
        Edit[edit<br/>文件编辑]
        Browser[browser<br/>浏览器]
        Command[command<br/>命令执行]
        MCP[mcp<br/>MCP工具]
        TaskGraph[task_graph<br/>任务图]
        Workflow[workflow<br/>工作流]
    end

    Orchestrator -->|管理| Plan
    Plan -->|计划| Do
    Do -->|执行| Check
    Check -->|检查| Act
    Act -->|改进| Plan

    Orchestrator -.->|所有工具| Read
    Orchestrator -.->|所有工具| Edit
    Orchestrator -.->|所有工具| Browser
    Orchestrator -.->|所有工具| Command
    Orchestrator -.->|所有工具| MCP
    Orchestrator -.->|所有工具| TaskGraph
    Orchestrator -.->|所有工具| Workflow

    Plan --> Read
    Plan --> Browser
    Plan --> MCP
    Plan --> TaskGraph
    Plan --> Workflow

    Do --> Read
    Do --> Edit
    Do --> Browser
    Do --> Command
    Do --> MCP
    Do --> Workflow

    Check --> Read
    Check --> Command
    Check --> Browser
    Check --> MCP

    Act --> Read
    Act --> Edit
    Act --> Browser
    Act --> MCP
    Act --> Workflow

    style Orchestrator fill:#ff6b6b,stroke:#c92a2a
    style Plan fill:#4ecdc4,stroke:#0ca678
    style Do fill:#95e1d3,stroke:#0ca678
    style Check fill:#ffd93d,stroke:#fab005
    style Act fill:#a8e6cf,stroke:#0ca678
```

## 6. 数据流图

```mermaid
graph LR
    subgraph "Input"
        User[用户输入]
        Config[配置文件]
        Skills[技能目录]
        Tools[工具定义]
    end

    subgraph "Processing"
        Agent[Agent]
        TaskEngine[TaskGraph Engine]
        LLM[LLM Provider]
        ToolExec[Tool Executor]
        Memory[Memory System]
    end

    subgraph "Output"
        Response[AI响应]
        FileChanges[文件变更]
        Events[事件流]
        Checkpoints[检查点]
    end

    subgraph "Storage"
        Workspace[Workspace]
        Conversation[Conversation]
        CheckpointStore[Checkpoint Storage]
        MemoryStore[Memory DB]
    end

    User --> Agent
    Config --> Agent
    Skills --> ToolExec
    Tools --> ToolExec

    Agent --> TaskEngine
    TaskEngine --> LLM
    TaskEngine --> ToolExec
    TaskEngine --> Memory

    LLM --> TaskEngine
    ToolExec --> TaskEngine
    Memory --> TaskEngine

    Agent --> Response
    ToolExec --> FileChanges
    Agent --> Events
    TaskEngine --> Checkpoints

    Agent --> Workspace
    Agent --> Conversation
    TaskEngine --> CheckpointStore
    Memory --> MemoryStore

    Workspace --> Agent
    Conversation --> Agent
    CheckpointStore --> TaskEngine
    MemoryStore --> Memory
```

## 7. 配置加载层级图

```mermaid
graph TD
    subgraph "4-Tier Configuration Loading"
        Builtin[Builtin<br/>内置配置<br/>dawei/内部]
        System[System<br/>系统配置<br/>/etc/dawei/]
        User["User<br/>用户配置<br/>~/.dawei/"]
        Workspace["Workspace<br/>工作空间配置<br/>{workspace}/.dawei/"]
    end

    subgraph "Configuration Types"
        ToolConfig[工具配置]
        ModeConfig[模式配置]
        SkillConfig[技能配置]
        LLMConfig[LLM配置]
        PluginConfig[插件配置]
    end

    subgraph "Priority Order"
        P1[优先级 1<br/>Workspace]
        P2[优先级 2<br/>User]
        P3[优先级 3<br/>System]
        P4[优先级 4<br/>Builtin]
    end

    Builtin --> ToolConfig
    Builtin --> ModeConfig
    Builtin --> SkillConfig
    Builtin --> LLMConfig
    Builtin --> PluginConfig

    System --> ToolConfig
    System --> ModeConfig
    System --> LLMConfig

    User --> ToolConfig
    User --> ModeConfig
    User --> SkillConfig
    User --> LLMConfig
    User --> PluginConfig

    Workspace --> ToolConfig
    Workspace --> ModeConfig
    Workspace --> SkillConfig
    Workspace --> LLMConfig

    Workspace -.-> P1
    User -.-> P2
    System -.-> P3
    Builtin -.-> P4

    style Workspace fill:#ff6b6b,stroke:#c92a2a
    style User fill:#ffd43b,stroke:#fab005
    style System fill:#74c0fc,stroke:#339af0
    style Builtin fill:#a9e34b,stroke:#51cf66
```

## 8. 事件驱动架构图

```mermaid
graph TB
    subgraph "Event Publishers"
        Agent[Agent]
        ToolExec[ToolExecutor]
        LLM[LLMProvider]
        TaskEngine[TaskGraphEngine]
        WebSocket[WebSocketManager]
    end

    subgraph "Event Bus"
        EventBus[EventBus<br/>core/events.py]
    end

    subgraph "Event Subscribers"
        WebSocketHandler[WebSocket Handlers]
        CheckpointMgr[CheckpointManager]
        Metrics[Metrics Collector]
        Logger[Logger]
        TUI[TUI Handler]
    end

    Agent -->|AGENT_START<br/>AGENT_COMPLETE<br/>AGENT_ERROR| EventBus
    ToolExec -->|TOOL_START<br/>TOOL_COMPLETE<br/>TOOL_ERROR| EventBus
    LLM -->|LLM_REQUEST<br/>LLM_RESPONSE<br/>LLM_ERROR| EventBus
    TaskEngine -->|TASK_NODE_START<br/>TASK_NODE_COMPLETE<br/>TASK_GRAPH_UPDATE| EventBus
    WebSocket -->|WS_CONNECTED<br/>WS_DISCONNECTED| EventBus

    EventBus -->|转发事件| WebSocketHandler
    EventBus -->|保存检查点| CheckpointMgr
    EventBus -->|收集指标| Metrics
    EventBus -->|记录日志| Logger
    EventBus -->|更新UI| TUI

    style EventBus fill:#ffd43b,stroke:#fab005,stroke-width:3px
```

## 9. 插件系统架构图

```mermaid
graph TB
    subgraph "Plugin Discovery (4-Tier)"
        BuiltinPlugins[Builtin Plugins<br/>dawei/plugins/]
        SystemPlugins[System Plugins<br/>/etc/dawei/plugins/]
        UserPlugins[User Plugins<br/>~/.dawei/plugins/]
        WorkspacePlugins["Workspace Plugins<br/>{workspace}/.dawei/plugins/"]
    end

    subgraph "Plugin Manager"
        Loader[PluginLoader<br/>加载插件]
        Validator[PluginValidator<br/>验证插件]
        Registry[PluginRegistry<br/>注册插件]
        Manager[PluginManager<br/>管理生命周期]
    end

    subgraph "Plugin Types"
        ToolPlugin[ToolPlugin<br/>工具插件]
        ServicePlugin[ServicePlugin<br/>服务插件]
        ChannelPlugin[ChannelPlugin<br/>通道插件]
        MemoryPlugin[MemoryPlugin<br/>记忆插件]
    end

    subgraph "Plugin Integration"
        ToolMgr[ToolManager]
        EventBus[EventBus]
        Memory[MemorySystem]
    end

    BuiltinPlugins --> Loader
    SystemPlugins --> Loader
    UserPlugins --> Loader
    WorkspacePlugins --> Loader

    Loader --> Validator
    Validator --> Registry
    Registry --> Manager

    Manager --> ToolPlugin
    Manager --> ServicePlugin
    Manager --> ChannelPlugin
    Manager --> MemoryPlugin

    ToolPlugin --> ToolMgr
    ServicePlugin --> EventBus
    ChannelPlugin --> EventBus
    MemoryPlugin --> Memory

    style Manager fill:#ff6b6b,stroke:#c92a2a
    style Registry fill:#ffd43b,stroke:#fab005
```

## 10. 记忆系统架构图

```mermaid
graph TB
    subgraph "Memory System"
        MemoryGraph[MemoryGraph<br/>时序知识图谱]
        VirtualContext[VirtualContextManager<br/>虚拟上下文管理]
        Gardener[MemoryGardener<br/>记忆园丁]
        Database[Memory Database<br/>SQLite]
    end

    subgraph "Memory Types"
        ShortTerm[短期记忆<br/>会话临时信息]
        LongTerm[长期记忆<br/>持久化知识]
        Working[工作记忆<br/>当前任务上下文]
        Episodic[情景记忆<br/>事件序列]
        Semantic[语义记忆<br/>概念和规则]
    end

    subgraph "Memory Operations"
        Store[存储<br/>store]
        Retrieve[检索<br/>retrieve]
        Update[更新<br/>update]
        Delete[删除<br/>delete]
        Search[搜索<br/>search]
        Consolidate[整合<br/>consolidate]
    end

    subgraph "Integration"
        Agent[Agent]
        ContextManager[ContextManager]
    end

    Agent --> MemoryGraph
    Agent --> VirtualContext
    Agent --> Gardener

    MemoryGraph --> ShortTerm
    MemoryGraph --> LongTerm
    MemoryGraph --> Working
    MemoryGraph --> Episodic
    MemoryGraph --> Semantic

    MemoryGraph --> Database
    VirtualContext --> MemoryGraph
    Gardener --> MemoryGraph
    Gardener --> Database

    MemoryGraph --> Store
    MemoryGraph --> Retrieve
    MemoryGraph --> Update
    MemoryGraph --> Delete
    MemoryGraph --> Search
    Gardener --> Consolidate

    VirtualContext --> ContextManager

    style MemoryGraph fill:#ff6b6b,stroke:#c92a2a
    style VirtualContext fill:#4ecdc4,stroke:#0ca678
    style Gardener fill:#ffd43b,stroke:#fab005
```

## 11. 技能系统架构图

```mermaid
graph TB
    subgraph "Skill Discovery (4-Tier Priority)"
        ModeSpecific["模式特定技能<br/>.dawei/skills-{mode}/"]
        GlobalModeSpecific["全局模式特定<br/>~/.dawei/skills-{mode}/"]
        ProjectGeneric["项目通用<br/>.dawei/skills/"]
        GlobalGeneric["全局通用<br/>~/.dawei/skills/"]
    end

    subgraph "Progressive Loading (3-Level)"
        Discovery[Discovery<br/>仅加载frontmatter]
        Instructions[Instructions<br/>加载SKILL.md内容]
        Resources[Resources<br/>访问资源文件]
    end

    subgraph "Skill Tools"
        ListSkills[list_skills<br/>列出技能]
        SearchSkills[search_skills<br/>搜索技能]
        GetSkill[get_skill<br/>获取技能]
        ListResources[list_skill_resources<br/>列资源]
        ReadResource[read_skill_resource<br/>读资源]
    end

    subgraph "Skill File Format"
        SKILL[SKILL.md]
        Frontmatter[Frontmatter<br/>name, description, license]
        Content[技能内容<br/>Markdown]
        ResourceFiles[资源文件<br/>reference.md, templates/]
    end

    ModeSpecific --> Discovery
    GlobalModeSpecific --> Discovery
    ProjectGeneric --> Discovery
    GlobalGeneric --> Discovery

    Discovery --> Instructions
    Instructions --> Resources

    Discovery --> ListSkills
    Discovery --> SearchSkills
    Instructions --> GetSkill
    Resources --> ListResources
    Resources --> ReadResource

    SKILL --> Frontmatter
    SKILL --> Content
    SKILL --> ResourceFiles

    style Discovery fill:#4ecdc4,stroke:#0ca678
    style Instructions fill:#ffd43b,stroke:#fab005
    style Resources fill:#ff6b6b,stroke:#c92a2a
```

## 12. 关键指标统计

- **总文件数**: 98 个 Python 文件
- **主模块数**: 24 个模块
- **代码行数**: 103,012 行
- **消息类型**: 61 种 WebSocket 消息类型
- **自定义工具**: 60 个工具类
- **模式数**: 5 个 PDCA 模式 (orchestrator, plan, do, check, act)
- **工具组**: 8 个组 (read, edit, browser, command, mcp, modes, task_graph, workflow)
- **插件类型**: 2 个基类 (ToolPlugin, ServicePlugin)
- **支持语言**: 3 种 (en, zh_CN, zh_TW)

## 13. 核心设计原则

1. **KISS (Keep It Simple, Stupid)** - 简化的实现
2. **DRY (Don't Repeat Yourself)** - 代码复用
3. **Fast Fail** - 快速失败原则
4. **Interface Segregation** - 接口隔离
5. **Single Responsibility** - 单一职责
6. **Open/Closed** - 开闭原则
7. **Dependency Inversion** - 依赖倒置

## 14. 架构模式

- **分层架构** - 清晰的关注点分离
- **事件驱动架构** - EventBus 实现松耦合
- **依赖注入** - DependencyContainer 管理服务
- **仓储模式** - 存储抽象层
- **策略模式** - 多 LLM 提供商、工具执行器
- **观察者模式** - EventBus 订阅者
- **工厂模式** - 工具工厂、客户端工厂
- **建造者模式** - A2UI 建造器、提示构建器
- **模板方法** - 基础处理器、基础工具
- **适配器模式** - 存储适配器、LLM 适配器
