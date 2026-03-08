export interface ScheduledTask {
  id: string;
  name: string;
  description?: string;
  cron: string;
  enabled: boolean;
  status: 'idle' | 'running' | 'success' | 'error';
  last_run?: string;
  next_run?: string;
  command: string;
  args?: string[];
  working_dir?: string;
}
