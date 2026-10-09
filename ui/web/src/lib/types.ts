export type OrbState = 'idle' | 'listening' | 'thinking' | 'speaking' | 'error';
export type ThemeName = 'cyan' | 'emerald' | 'crimson';

export type PanelId =
  | 'home'
  | 'chat'
  | 'agent-town'
  | 'tasks'
  | 'coding'
  | 'memory'
  | 'world-monitor'
  | 'system'
  | 'settings';

export type ConnectionState = 'connecting' | 'open' | 'closed';

export interface UiSettings {
  theme: ThemeName;
  accent: string;
  performance_mode: boolean;
  reduce_motion: boolean;
}

export interface ModelSettings {
  fast: string;
  strong: string;
  routing: 'auto' | 'fast' | 'strong';
}

export interface VoiceSettings {
  tts_provider: string;
  tts_model: string;
  tts_fallback_model: string;
  stt_engine: string;
  stt_model: string;
  language: string;
  wake_word_enabled: boolean;
}

export interface Settings {
  version: number;
  log_level: string;
  memory_enabled: boolean;
  ui: UiSettings;
  api: { host: string; port: number };
  models: ModelSettings;
  voice: VoiceSettings;
  limits: { daily_usd: number; monthly_usd: number; hard_stop: boolean };
  security: {
    allowed_folders: string[];
    allowed_apps: string[];
    allowed_domains: string[];
    allowed_commands: string[];
  };
}

export interface SecretStatus {
  source: string;
  masked: string;
  prefix_ok: boolean;
}

export interface SecretsResponse {
  keyring_available: boolean;
  secrets: Record<string, SecretStatus>;
}

export interface Diagnostics {
  nova_version: string;
  python: string;
  platform: string;
  machine: string;
  paths: Record<string, unknown>;
  settings: Record<string, unknown>;
  secrets: Record<string, unknown>;
  warnings: string[];
  core?: Record<string, unknown>;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  model?: string;
  streaming?: boolean;
  error?: boolean;
}
