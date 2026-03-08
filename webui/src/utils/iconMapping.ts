/**
 * Iconify 图标映射配置
 *
 * 从 Element Plus 图标迁移到 Iconify 图标
 * 参考: https://icon-sets.iconify.design/
 *
 * 设计原则：
 * 1. 使用 Lucide 图标集 (一致性更好，现代设计)
 * 2. 使用 Material Symbols 图标集 (语义清晰)
 * 3. 保持视觉一致性
 */

import type { IconifyIcon } from '@iconify/vue';

// ========== 左侧边栏功能按钮 ==========

/**
 * 语言模型 (LLM Providers)
 * 功能：管理AI语言模型配置
 * 选择：brain - 表示AI智能和语言理解
 */
export const ICON_LLM_PROVIDER = 'lucide:brain';

/**
 * 技能 (Skills)
 * 功能：管理和配置AI技能
 * 选择：sparkles - 表示技能和魔法效果
 */
export const ICON_SKILLS = 'lucide:sparkles';

/**
 * 智能体 (Agents)
 * 功能：管理AI智能体
 * 选择：bot - 表示AI机器人助手
 */
export const ICON_AGENTS = 'lucide:bot';

/**
 * 插件 (Plugins)
 * 功能：管理系统插件
 * 选择：puzzle - 表示插件和扩展功能
 */
export const ICON_PLUGINS = 'lucide:puzzle';

/**
 * MCP 服务器 (MCP Servers)
 * 功能：管理模型上下文协议服务器
 * 选择：server - 表示服务器和网络连接
 */
export const ICON_MCP = 'lucide:server';

/**
 * 定时任务 (Scheduled Tasks)
 * 功能：管理定时执行的任务
 * 选择：timer - 表示定时和调度
 */
export const ICON_SCHEDULED_TASKS = 'lucide:timer';

// ========== 通用操作图标 ==========

/**
 * 创建/添加
 * 选择：circle-plus - 清晰的添加意图
 */
export const ICON_ADD = 'lucide:circle-plus';

/**
 * 编辑
 * 选择：pencil - 通用的编辑图标
 */
export const ICON_EDIT = 'lucide:pencil';

/**
 * 删除
 * 选择：trash-2 - 清晰的删除意图
 */
export const ICON_DELETE = 'lucide:trash-2';

/**
 * 刷新
 * 选择：refresh-cw - 现代化的刷新图标
 */
export const ICON_REFRESH = 'lucide:refresh-cw';

/**
 * 搜索
 * 选择：search - 标准的搜索图标
 */
export const ICON_SEARCH = 'lucide:search';

/**
 * 设置
 * 选择：settings - 标准的设置图标
 */
export const ICON_SETTINGS = 'lucide:settings';

/**
 * 市场购物
 * 选择：shopping-cart - 标准的购物车图标
 */
export const ICON_SHOPPING_CART = 'lucide:shopping-cart';

/**
 * 文档
 * 选择：file-text - 文档文件图标
 */
export const ICON_DOCUMENT = 'lucide:file-text';

/**
 * 加载中
 * 选择：loader-2 - 现代化的加载动画
 */
export const ICON_LOADING = 'lucide:loader-2';

/**
 * 复制
 * 选择：copy - 标准的复制图标
 */
export const ICON_COPY = 'lucide:copy';

/**
 * 向下箭头
 * 选择：chevron-down - 现代化的向下箭头
 */
export const ICON_ARROW_DOWN = 'lucide:chevron-down';

/**
 * 关闭
 * 选择：x - 清晰的关闭意图
 */
export const ICON_CLOSE = 'lucide:x';

/**
 * 用户
 * 选择：user - 标准的用户图标
 */
export const ICON_USER = 'lucide:user';

/**
 * 锁
 * 选择：lock - 标准的锁定图标
 */
export const ICON_LOCK = 'lucide:lock';

/**
 * 链接
 * 选择：link - 标准的链接图标
 */
export const ICON_LINK = 'lucide:link';

/**
 * 折叠
 * 选择：fold-vertical - 垂直折叠
 */
export const ICON_FOLD = 'lucide:fold-vertical';

/**
 * 展开
 * 选择：unfold-vertical - 垂直展开
 */
export const ICON_EXPAND = 'lucide:unfold-vertical';

/**
 * 切换
 * 选择：swap - 交换和切换
 */
export const ICON_SWITCH = 'lucide:swap';

/**
 * 网格
 * 选择：grid - 标准的网格图标
 */
export const ICON_GRID = 'lucide:grid';

/**
 * 文件夹
 * 选择：folder - 标准的文件夹图标
 */
export const ICON_FOLDER = 'lucide:folder';

/**
 * 文件夹打开
 * 选择：folder-open - 打开的文件夹
 */
export const ICON_FOLDER_OPEN = 'lucide:folder-open';

/**
 * CPU
 * 选择：cpu - 处理器图标
 */
export const ICON_CPU = 'lucide:cpu';

/**
 * 放大
 * 选择：zoom-in - 放大图标
 */
export const ICON_ZOOM_IN = 'lucide:zoom-in';

/**
 * 缩小
 * 选择：zoom-out - 缩小图标
 */
export const ICON_ZOOM_OUT = 'lucide:zoom-out';

/**
 * 菜单
 * 选择：menu - 标准的菜单图标
 */
export const ICON_MENU = 'lucide:menu';

/**
 * 聊天
 * 选择：message-circle - 聊天气泡
 */
export const ICON_CHAT = 'lucide:message-circle';

/**
 * 问题
 * 选择：help-circle - 问号圆圈
 */
export const ICON_QUESTION = 'lucide:help-circle';

// ========== Iconify 图标类型定义 ==========

/**
 * Iconify 图标名称类型
 */
export type IconifyIconName =
  | 'lucide:brain'
  | 'lucide:sparkles'
  | 'lucide:bot'
  | 'lucide:puzzle'
  | 'lucide:server'
  | 'lucide:timer'
  | 'lucide:circle-plus'
  | 'lucide:pencil'
  | 'lucide:trash-2'
  | 'lucide:refresh-cw'
  | 'lucide:search'
  | 'lucide:settings'
  | 'lucide:shopping-cart'
  | 'lucide:file-text'
  | 'lucide:loader-2'
  | 'lucide:copy'
  | 'lucide:chevron-down'
  | 'lucide:x'
  | 'lucide:user'
  | 'lucide:lock'
  | 'lucide:link'
  | 'lucide:fold-vertical'
  | 'lucide:unfold-vertical'
  | 'lucide:swap'
  | 'lucide:grid'
  | 'lucide:folder'
  | 'lucide:folder-open'
  | 'lucide:cpu'
  | 'lucide:zoom-in'
  | 'lucide:zoom-out'
  | 'lucide:menu'
  | 'lucide:message-circle'
  | 'lucide:help-circle';

/**
 * Iconify 图标组件 Props
 */
export interface IconifyProps {
  icon: IconifyIconName;
  width?: string | number;
  height?: string | number;
  color?: string;
  inline?: boolean;
}
