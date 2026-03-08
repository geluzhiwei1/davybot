export interface Skill {
  name: string;
  icon?: string;
  description: string;
  category?: string;
  mode?: string;
  scope: 'workspace' | 'user' | 'system';
  path?: string;
  has_instructions?: boolean;
  has_resources?: boolean;
  resource_count?: number;
}
