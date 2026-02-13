/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/**
 * Language detection and extension mapping for CodeMirror
 */

export interface LanguageInfo {
  name: string
  extensions: string[]
  mimetypes?: string[]
}

export const LANGUAGE_MAP: Readonly<Record<string, LanguageInfo>> = {
  python: {
    name: 'Python',
    extensions: ['.py', '.pyi', '.pyw'],
    mimetypes: ['text/x-python'],
  },
  javascript: {
    name: 'JavaScript',
    extensions: ['.js', '.mjs', '.cjs'],
    mimetypes: ['text/javascript', 'application/javascript'],
  },
  typescript: {
    name: 'TypeScript',
    extensions: ['.ts', '.mts', '.cts'],
    mimetypes: ['text/typescript'],
  },
  jsx: {
    name: 'JSX',
    extensions: ['.jsx'],
    mimetypes: ['text/jsx'],
  },
  tsx: {
    name: 'TSX',
    extensions: ['.tsx'],
    mimetypes: ['text/tsx'],
  },
  html: {
    name: 'HTML',
    extensions: ['.html', '.htm'],
    mimetypes: ['text/html'],
  },
  css: {
    name: 'CSS',
    extensions: ['.css'],
    mimetypes: ['text/css'],
  },
  json: {
    name: 'JSON',
    extensions: ['.json', '.jsonc'],
    mimetypes: ['application/json'],
  },
  vue: {
    name: 'Vue',
    extensions: ['.vue'],
    mimetypes: ['text/x-vue'],
  },
  xml: {
    name: 'XML',
    extensions: ['.xml', '.xsl', '.xsd'],
    mimetypes: ['text/xml', 'application/xml'],
  },
  markdown: {
    name: 'Markdown',
    extensions: ['.md', '.markdown', '.mdown'],
    mimetypes: ['text/markdown', 'text/x-markdown'],
  },
  yaml: {
    name: 'YAML',
    extensions: ['.yaml', '.yml'],
    mimetypes: ['text/x-yaml', 'application/x-yaml'],
  },
  sql: {
    name: 'SQL',
    extensions: ['.sql'],
    mimetypes: ['text/x-sql', 'application/sql'],
  },
  shell: {
    name: 'Shell',
    extensions: ['.sh', '.bash', '.zsh'],
    mimetypes: ['text/x-shellscript', 'application/x-sh'],
  },
  plaintext: {
    name: 'Plain Text',
    extensions: ['.txt', '.text'],
    mimetypes: ['text/plain'],
  },
} as const

// Build extension lookup map for performance
const EXTENSION_MAP = Object.freeze(
  Object.entries(LANGUAGE_MAP).reduce<Record<string, string>>(
    (acc, [lang, info]) => {
      info.extensions.forEach((ext) => {
        acc[ext] = lang
      })
      return acc
    },
    {}
  )
)

/**
 * Get language identifier from file path
 * @param filePath - File path to analyze
 * @returns Language identifier (defaults to 'plaintext')
 */
export function getLanguageFromPath(filePath: string): string {
  if (!filePath) return 'plaintext'

  const ext = filePath.includes('.')
    ? filePath.slice(filePath.lastIndexOf('.'))
    : ''

  return EXTENSION_MAP[ext] ?? 'plaintext'
}

/**
 * Check if a file path matches a specific language
 * @param filePath - File path to check
 * @param language - Language identifier to match
 */
export function isLanguageOfFile(filePath: string, language: string): boolean {
  return getLanguageFromPath(filePath) === language
}

/**
 * Get all supported file extensions
 */
export function getSupportedExtensions(): string[] {
  return Object.keys(EXTENSION_MAP)
}
