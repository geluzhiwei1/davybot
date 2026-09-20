export interface UserPreferences {
  language: string;
  timezone: string;
  theme: "light" | "dark" | "auto";
  fontSize: number;
  autoSave: boolean;
  compactMode: boolean;
}

export interface UserProfile {
  id: string;
  nickname: string;
  email?: string;
  phone?: string;
  avatar?: string;
  plan: string;
  tokenQuota: number;
  tokenUsed: number;
  createdAt: string;
  preferences: UserPreferences;
}

export interface KeyboardShortcut {
  id: string;
  name: string;
  keys: string;
  category: string;
  description?: string;
  editable?: boolean;
}
