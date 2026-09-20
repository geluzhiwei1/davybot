/**
 * Skills type definitions — migrated from legalbot/webui/src/types/skills.ts
 */

export type SkillScope = "workspace" | "user" | "system";

export interface Skill {
  name: string;
  icon?: string;
  description: string;
  category?: string;
  mode?: string;
  scope: SkillScope;
  path?: string;
  has_instructions?: boolean;
  has_resources?: boolean;
  resource_count?: number;
}

export interface SkillFileItem {
  name: string;
  path: string;
  type: "file" | "directory";
  size?: number;
  children?: SkillFileItem[];
}

export interface SkillContent {
  name: string;
  path: string;
  content: string;
  language?: string;
}

export interface CreateSkillParams {
  name: string;
  description: string;
  mode?: string;
  scope?: SkillScope;
  content?: string;
}

export interface SkillFilter {
  mode: string;
  scope: string;
  search: string;
}
