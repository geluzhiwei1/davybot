export interface Agent {
  slug: string;
  name: string;
  description: string;
  is_default: boolean;
  source: 'system' | 'user' | 'workspace';
  role_definition?: string;
  when_to_use?: string;
  groups?: string[];
  custom_instructions?: string;
}
