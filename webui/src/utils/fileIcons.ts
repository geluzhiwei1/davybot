/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/**
 * 文件类型图标映射工具
 * 根据文件扩展名返回对应的 Element Plus 图标组件
 */

import {
  Folder,
  Document,
  Picture,
  VideoCamera,
  Headset,
  Files,
  Setting,
  DataAnalysis,
  Connection,
  Management,
  EditPen,
  Ticket,
  Link,
  Box,
  Memo,
  Present,
  Brush,
  Monitor,
  Stamp,
  Download,
  Grid
} from '@element-plus/icons-vue'

// 图标组件类型定义
export type FileIconComponent = typeof Folder

/**
 * 文件扩展名到图标的映射
 */
const FILE_ICONS: Record<string, FileIconComponent> = {
  // ==================== 文档类 ====================
  'pdf': Document,
  'doc': Document,
  'docx': Document,
  'dot': Document,
  'dotx': Document,
  'odt': Document,
  'rtf': Document,
  'tex': Document,
  'wpd': Document,
  'pages': Document,

  // ==================== 表格类 ====================
  'xls': DataAnalysis,
  'xlsx': DataAnalysis,
  'xlsm': DataAnalysis,
  'xlsb': DataAnalysis,
  'csv': DataAnalysis,
  'tsv': DataAnalysis,
  'ods': DataAnalysis,

  // ==================== 演示文稿类 ====================
  'ppt': Present,
  'pptx': Present,
  'pps': Present,
  'ppsx': Present,
  'odp': Present,
  'key': Present,

  // ==================== 图片类 ====================
  'jpg': Picture,
  'jpeg': Picture,
  'png': Picture,
  'gif': Picture,
  'bmp': Picture,
  'svg': Picture,
  'webp': Picture,
  'ico': Picture,
  'tiff': Picture,
  'tif': Picture,
  'psd': Picture,
  'ai': Picture,
  'eps': Picture,
  'raw': Picture,
  'heic': Picture,
  'avif': Picture,

  // ==================== 视频类 ====================
  'mp4': VideoCamera,
  'avi': VideoCamera,
  'mkv': VideoCamera,
  'mov': VideoCamera,
  'wmv': VideoCamera,
  'flv': VideoCamera,
  'webm': VideoCamera,
  'm4v': VideoCamera,
  'mpeg': VideoCamera,
  'mpg': VideoCamera,
  '3gp': VideoCamera,
  'ogv': VideoCamera,

  // ==================== 音频类 ====================
  'mp3': Headset,
  'wav': Headset,
  'flac': Headset,
  'aac': Headset,
  'ogg': Headset,
  'wma': Headset,
  'm4a': Headset,
  'opus': Headset,
  'aiff': Headset,

  // ==================== 压缩文件类 ====================
  'zip': Box,
  'rar': Box,
  '7z': Box,
  'tar': Box,
  'gz': Box,
  'bz2': Box,
  'xz': Box,
  'z': Box,
  'cab': Box,
  'iso': Box,
  'dmg': Box,
  'pkg': Box,
  'deb': Box,
  'rpm': Box,

  // ==================== 代码类 ====================
  'js': EditPen,  // Code 不存在，使用 EditPen
  'jsx': EditPen,
  'ts': EditPen,
  'tsx': EditPen,
  'vue': EditPen,
  // 'html': 在后面定义 (Monitor)
  // 'htm': 使用与 html 相同的图标
  // 'css', 'scss', 'sass', 'less' 在后面定义 (Brush)
  // 'json': 使用 Document
  // 'xml': 在后面定义 (Connection)
  'yaml': EditPen,
  'yml': EditPen,
  'toml': EditPen,
  'ini': EditPen,
  'conf': EditPen,
  'config': EditPen,

  'py': EditPen,
  'pyc': EditPen,
  'pyd': EditPen,
  'pyo': EditPen,
  'pyw': EditPen,
  'pyz': EditPen,
  'ipynb': EditPen,

  'java': EditPen,
  'jar': EditPen,
  'class': EditPen,
  'kotlin': EditPen,
  'scala': EditPen,
  'groovy': EditPen,

  'c': EditPen,
  'cpp': EditPen,
  'cc': EditPen,
  'cxx': EditPen,
  'h': EditPen,
  'hpp': EditPen,
  'm': EditPen,
  'mm': EditPen,
  'swift': EditPen,
  'objc': EditPen,
  'go': EditPen,
  'rs': EditPen,
  'rust': EditPen,

  'php': EditPen,
  'phtml': EditPen,
  'rb': EditPen,
  'gem': EditPen,
  'gemspec': EditPen,

  'cs': EditPen,
  'vb': EditPen,
  'fs': EditPen,
  'fsx': EditPen,

  'sh': EditPen,
  'bash': EditPen,
  'zsh': EditPen,
  'fish': EditPen,
  'ps1': EditPen,
  'bat': EditPen,
  'cmd': EditPen,
  'powershell': EditPen,

  'sql': DataAnalysis,
  'db': DataAnalysis,
  'sqlite': DataAnalysis,
  'mdb': DataAnalysis,
  'accdb': DataAnalysis,

  'r': EditPen,
  'rmd': EditPen,
  'matlab': EditPen,
  'lua': EditPen,
  'pl': EditPen,
  'pm': EditPen,

  // ==================== Markdown 和 文本类 ====================
  'md': Memo,
  'markdown': Memo,
  'txt': Document,
  'text': Document,
  'log': Document,
  'readme': Document,

  // ==================== 配置文件类 ====================
  'env': Setting,
  'gitignore': Ticket,
  'gitattributes': Ticket,
  'dockerignore': Ticket,
  'eslint': Ticket,
  'eslintrc': Ticket,
  'prettierrc': Ticket,
  'prettier': Ticket,
  'babelrc': Ticket,
  'editorconfig': Ticket,

  // ==================== 版本控制类 ====================
  'git': Link,
  'svn': Link,
  'hg': Link,

  // ==================== 数据类 ====================
  'xml': Connection,
  'rdf': Connection,
  'jsonld': Connection,
  'n3': Connection,
  'nt': Connection,
  'ttl': Connection,

  // ==================== 网络类 ====================
  'html': Monitor,
  'css': Brush,
  'scss': Brush,
  'sass': Brush,
  'less': Brush,

  // ==================== 字体类 ====================
  'ttf': Management,
  'otf': Management,
  'woff': Management,
  'woff2': Management,
  'eot': Management,

  // ==================== 数据库类 ====================
  'sqlite3': DataAnalysis,

  // ==================== 其他常见文件类 ====================
  'exe': Management,
  'dll': Management,
  'so': Management,
  'dylib': Management,
  'app': Management,

  'img': Stamp,

  'torrent': Download,

  'lock': Ticket,

  'cer': Stamp,
  'crt': Stamp,
  'pem': Stamp,
  'der': Stamp,

  'p12': Stamp,
  'pfx': Stamp,

  // ==================== 项目和构建文件 ====================
  'package': Box,
  'gradle': EditPen,
  'pom': EditPen,
  'manifest': EditPen,
  'makefile': EditPen,
  'dockerfile': EditPen,
  'docker-compose': EditPen,
  'vagrantfile': EditPen,
  'procfile': EditPen,
  'rakefile': EditPen,
  'gemfile': EditPen,
  'composer': EditPen,
  'podfile': EditPen,
  'cartfile': EditPen,
  'podspec': EditPen,
  'workspaceroot': Files,

  // ==================== IDE 和编辑器文件 ====================
  'suo': Grid,
  'sln': Grid,
  'vcxproj': Grid,
  'csproj': Grid,
  'vbproj': Grid,
  'fsproj': Grid,
  'xcode': Files,
  'xcworkspace': Files,
  'pbxproj': Files,
  'plist': Files,

  // ==================== 测试文件 ====================
  'spec': EditPen,
  'test': EditPen,
  'tests': EditPen,
  'spec.ts': EditPen,
  'test.ts': EditPen,
  'spec.js': EditPen,
  'test.js': EditPen,
  'spec.py': EditPen,
  'test.py': EditPen,
  'e2e': EditPen,
  'integration': EditPen,

  // ==================== 备份文件 ====================
  'bak': Files,
  'backup': Files,
  'old': Files,
  'tmp': Files,
  'temp': Files
}

/**
 * 根据文件名获取图标组件
 * @param fileName - 文件名
 * @returns 对应的图标组件
 */
export function getFileIcon(fileName: string): FileIconComponent {
  if (!fileName) {
    return Document
  }

  // 提取文件扩展名
  const parts = fileName.split('.')
  const ext = parts.length > 1 ? parts[parts.length - 1].toLowerCase() : ''

  // 如果有映射，返回对应的图标
  if (ext && FILE_ICONS[ext]) {
    return FILE_ICONS[ext]
  }

  // 特殊文件名检测（不带扩展名的配置文件）
  const lowerFileName = fileName.toLowerCase()

  if (lowerFileName === 'makefile' || lowerFileName === 'dockerfile') {
    return Code
  }

  if (lowerFileName === 'license' || lowerFileName === 'readme') {
    return Document
  }

  if (lowerFileName === 'gitignore' || lowerFileName === 'dockerignore') {
    return Ticket
  }

  if (lowerFileName === 'package.json' || lowerFileName === 'package-lock.json') {
    return Box
  }

  if (lowerFileName === 'tsconfig.json' || lowerFileName === 'jsconfig.json') {
    return Setting
  }

  if (lowerFileName === '.env' || lowerFileName === '.env.example') {
    return Setting
  }

  if (lowerFileName === 'yarn.lock' || lowerFileName === 'package-lock.json') {
    return Ticket
  }

  // 默认返回文档图标
  return Document
}

/**
 * 根据文件类型获取图标组件
 * @param fileType - 文件类型 ('file' | 'folder')
 * @param fileName - 文件名（可选，用于更精确的图标选择）
 * @returns 对应的图标组件
 */
export function getFileIconByType(fileType: 'file' | 'folder', fileName?: string): FileIconComponent {
  if (fileType === 'folder') {
    return Folder
  }

  if (fileName) {
    return getFileIcon(fileName)
  }

  return Document
}

/**
 * 获取文件图标颜色
 * @param fileName - 文件名
 * @returns CSS 颜色值
 */
export function getFileIconColor(fileName: string): string {
  if (!fileName) {
    return 'var(--el-text-color-primary)'
  }

  const ext = fileName.split('.').pop()?.toLowerCase() || ''
  const lowerFileName = fileName.toLowerCase()

  // 文档类 - 蓝色
  if (['pdf', 'doc', 'docx', 'txt', 'md', 'rtf'].includes(ext)) {
    return '#409EFF'
  }

  // 表格类 - 绿色
  if (['xls', 'xlsx', 'csv'].includes(ext)) {
    return '#67C23A'
  }

  // 演示文稿类 - 橙色
  if (['ppt', 'pptx'].includes(ext)) {
    return '#E6A23C'
  }

  // 图片类 - 紫色
  if (['jpg', 'jpeg', 'png', 'gif', 'svg', 'bmp', 'webp'].includes(ext)) {
    return '#F56C6C'
  }

  // 视频类 - 红色
  if (['mp4', 'avi', 'mkv', 'mov'].includes(ext)) {
    return '#F56C6C'
  }

  // 音频类 - 青色
  if (['mp3', 'wav', 'flac', 'aac'].includes(ext)) {
    return '#17B3A8'
  }

  // 代码类 - 深紫色
  const codeExts = ['js', 'jsx', 'ts', 'tsx', 'vue', 'py', 'java', 'go', 'rs', 'php', 'rb', 'cs']
  if (codeExts.includes(ext)) {
    return '#6F7AD3'
  }

  // 压缩文件 - 灰色
  if (['zip', 'rar', '7z', 'tar', 'gz'].includes(ext)) {
    return '#909399'
  }

  // 配置文件 - 深蓝色
  if (['env', 'json', 'yaml', 'yml', 'toml', 'ini', 'conf'].includes(ext) ||
      lowerFileName.includes('config') || lowerFileName === 'makefile' || lowerFileName === 'dockerfile') {
    return '#3A8EE6'
  }

  // 数据库 - 蓝绿色
  if (['sql', 'db', 'sqlite'].includes(ext)) {
    return '#00CED1'
  }

  return 'var(--el-text-color-primary)'
}
