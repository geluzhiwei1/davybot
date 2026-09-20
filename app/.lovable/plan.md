## 优化方案

### 一、智能体专家头像 icon 重设计（点 1）

**现状**：所有 12 位专家头像都用同一个 `Cloud` 图标 + 不同色相渐变，仅靠颜色区分，识别度低；圆角矩形 `rounded-2xl` 与"专家/人物"语义弱关联。

**改造方案 — `src/components/expert-icon.tsx`**：

1. **每位专家专属图标**：在 `src/lib/experts.ts` 给每条 EXPERT 加 `icon` 字段（lucide 图标名），按业务语义匹配：

| 专家     | 图标          | 专家       | 图标         |
| -------- | ------------- | ---------- | ------------ |
| 制裁合规 | `ShieldAlert` | 反垄断     | `Gavel`      |
| 出口管制 | `Container`   | ESG        | `Leaf`       |
| 数据合规 | `Database`    | 产品质量   | `BadgeCheck` |
| 境外投资 | `Globe2`      | 反商业贿赂 | `HandCoins`  |
| 知识产权 | `Lightbulb`   | 海外税务   | `Receipt`    |
| 劳动用工 | `Users`       | 供应链     | `Network`    |

2. **视觉升级**：
   - 形状统一改为更现代的 `rounded-xl`（中尺寸）/`rounded-lg`（小尺寸），并提供 `shape="circle"` 选项给堆叠场景使用；
   - 渐变保留但降低饱和度，加内圈高光 `bg-gradient-to-br + inset shadow`，移除粗 `drop-shadow` 粗描边，整体更克制；
   - `ring-1 ring-white/15` 改为 `ring-1 ring-white/10`，stroke 由 2.2 调到 2 与界面一致。
3. `ExpertIcon` API 增加可选 `icon?: LucideIcon` 兜底回退到 `Cloud`，向后兼容。

### 二、侧边栏收起效果优化（点 2）

**现状问题**（`app-sidebar.tsx` + `ui/sidebar.tsx`）：

- 收起后宽度 `3rem`，但工作空间分组、临时任务分组、AI 业务、探索全部保留 `SidebarGroupLabel`（中文标签裁切难看）；
- 工作空间项收起时仍渲染 `ChevronRight + Folder + 文字 + count + 操作按钮` 的复合行，被裁出溢出残影；
- 收起态下两个"+"按钮（创建工作空间、新临时任务）都在中央，但分组分隔不清，重复堆叠。

**改造方案**：

1. **隐藏所有 `SidebarGroupLabel`**（只在 `!collapsed` 渲染），收起态用 4px 高的小色块分隔代替。
2. **工作空间收起态简化**：只渲染单个 `Folder` 图标按钮（带 Tooltip 显示"工作空间名 · N 任务"），点击直接跳转该空间下首个/最近任务；当前激活空间保留左侧 2px brand 竖条。
3. **临时任务收起态**：只渲染最近 3 条临时任务，每条用一个 `MessageSquare` 圆形小图标代替（Tooltip 显示标题），其余折叠到 `MoreHorizontal` 弹出菜单。
4. **AI 业务 / 探索 / 设置收起态**：保留单图标按钮，统一垂直间距 `py-1`，加 Tooltip。
5. **顶部 Logo 区域收起时**：去掉 `LexAgent` 文字，只保留渐变色 Scale 图标，整体居中。
6. **过渡**：所有 row 加 `transition-[padding,gap] duration-150`，避免文本/图标抖动。

### 三、输入框遮盖对话框文字（点 3）

**现状问题**（`chat-view.tsx` + `floating-input.tsx`）：

- 消息列表 `flex-1 overflow-y-auto`，底部 `FloatingInput` 用 `sticky bottom-0` 浮在内容上方；
- `FloatingInput` 高度约 140-200px（含 chips + textarea + toolbar + 免责声明），最后一条消息会被永久遮住；
- 没有底部 padding，也没有遮罩淡入，message-bubble 会被 textarea 切断。

**改造方案**：

1. **消息容器加底部留白**：`max-w-3xl mx-auto py-6 space-y-5 px-2` → `pb-[200px]`（响应 chips 显示与否动态调整：基础 `pb-44`，有 chips 时 `pb-56`）。最新消息发出后 `scrollIntoView` 仍能露出全部气泡。
2. **输入框上方加渐变遮罩**：在 `FloatingInput` 顶部插入一个 `h-6 -mt-6 bg-gradient-to-b from-transparent to-background pointer-events-none` 的渐隐层，让最后一条消息淡出而不是被硬切。
3. **scroll 行为修正**：`scrollRef.current.scrollTo` 的 `top` 加上输入框实际高度（用 ref 量 FloatingInput 高度，写入 CSS var `--input-h`，messages 容器用 `padding-bottom: var(--input-h)`），保证发完消息后 last bubble 不被覆盖。
4. **glass 模糊降级**：`FloatingInput` 外层 `glass` 当前透明度过高导致下方文字隐约可见反而干扰阅读，改为 `bg-background/95 backdrop-blur-md`，对比更清晰。

### 四、整体精简清单（点 4）

逐处去冗，**不改功能**：

| #   | 位置                                 | 现状                                                                                         | 精简动作                                                                             |
| --- | ------------------------------------ | -------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------ |
| 1   | `chat-view.tsx` 顶部 context bar     | `团队协作` Badge + 专家 Badge + `浏览文件 · N` 按钮 三件并列                                 | 去掉 `团队协作` Badge（输入框内已有"团队协作"按钮态显示，重复）；保留专家 + 浏览文件 |
| 2   | `floating-input.tsx` 右下角          | `多智能体协作` 小徽标 与左侧"团队协作"按钮重复                                               | 删除右下角徽标                                                                       |
| 3   | `floating-input.tsx` 底部免责声明    | "AI 生成内容仅供参考…本期为 UI 原型，回复为 mock 数据" 两句                                  | 合并成一句："AI 生成内容仅供参考。" mock 提示移至全局 header tooltip                 |
| 4   | `chat-view.tsx` 工作空间 EmptyState  | 标题区 14×14 大图标 + h2 + 副标题 + 文件卡片标题 + 文件卡片副标题（"为这个空间添加文件后…"） | 去掉副标题与文件卡片重复说明，标题图标缩到 10×10                                     |
| 5   | `chat-view.tsx` 临时任务 EmptyState  | 16×16 大图标 + h2 + 副标题 + "选择专家开始咨询 · N 位" + "← 左右滑动 →"                      | 去掉"← 左右滑动 →"提示（已有 overflow chip 视觉），副标题保留一句                    |
| 6   | `index.tsx` Hero                     | 顶部小徽标 "12 位法律 AI 专家 · 团队协作" + 大标题 + 副文 + 两按钮                           | 去掉顶部小徽标（信息已在副文呈现）                                                   |
| 7   | `app-sidebar.tsx` 工作空间分组标签   | "工作空间 · N 个 · M 任务"                                                                   | 简化为 "工作空间 · N"（任务数已在每个空间末尾 badge 显示）                           |
| 8   | `floating-input.tsx` "可选" 文字分隔 | "已配置堆叠 \| 可选 chip1 chip2 …"                                                           | 去掉"可选"文字，只保留 1px 竖分隔线                                                  |

### 五、技术实现概要

**新增**：

- `src/lib/experts.ts`：每条 EXPERT 增加 `icon: LucideIcon` 字段。

**修改**：

- `src/components/expert-icon.tsx`：接受 `icon` prop（向后兼容默认 Cloud）；新增 `shape?: "rounded" | "circle"`；视觉调整。
- `src/components/app-sidebar.tsx`：分组 label / 工作空间行 / 临时任务行的 collapsed 分支重写为单图标 + Tooltip 形态；顶部 Logo collapsed 简化；分组标签精简文案。
- `src/components/chat-view.tsx`：messages 容器加 `pb-[var(--input-h)]`；EmptyState 文案/图标精简；context bar 去 `团队协作` Badge。
- `src/components/floating-input.tsx`：用 `useRef + ResizeObserver` 写入 CSS var `--input-h` 到祖先；顶部加渐变遮罩；删除"多智能体协作"徽标；底部文字合并；"可选"文字改竖线。
- `src/routes/index.tsx`：去掉 Hero 顶部小徽标。

### 不在本轮范围

- 实际更换专家图标库（如自定义 SVG / lottie）—— 仍用 lucide-react 内置
- 侧边栏宽度可拖拽调整
- 移动端 sheet 模式优化
- 消息列表虚拟滚动
