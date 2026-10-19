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

export interface ProviderSettings {
  name: 'gemini' | 'mock';
  proxy_mode: 'bypass' | 'system' | 'manual';
  proxy_url: string;
  timeout_seconds: number;
  max_retries: number;
  tools_enabled: boolean;
  context_window_messages: number;
  summarize_after_messages: number;
}

export interface PricingSettings {
  tier: 'free' | 'paid';
}

export interface PrivacySettings {
  notice_acknowledged: boolean;
  remind_before_attach: boolean;
}

export interface LimitSettings {
  enabled: boolean;
  daily_usd: number;
  monthly_usd: number;
  hard_stop: boolean;
}

export interface VoiceSettings {
  tts_provider: string;
  stt_engine: string;
  language: string;
}

export interface Settings {
  version: number;
  log_level: string;
  memory_enabled: boolean;
  ui: UiSettings;
  api: { host: string; port: number };
  models: ModelSettings;
  voice: VoiceSettings;
  limits: LimitSettings;
  security: {
    allowed_folders: string[];
    allowed_apps: string[];
    allowed_domains: string[];
    allowed_commands: string[];
  };
  provider: ProviderSettings;
  pricing: PricingSettings;
  privacy: PrivacySettings;
}

export interface SecretStatus {
  source: string;
  masked: string;
  prefix_ok: boolean;
}

export interface BrainStatus {
  mode: 'live' | 'demo' | 'needs_key';
  provider: 'gemini' | 'mock';
  has_gemini_key: boolean;
  has_elevenlabs_key: boolean;
}

export type VoiceState =
  | 'idle'
  | 'listening'
  | 'transcribing'
  | 'thinking'
  | 'speaking'
  | 'error';

export interface VoiceDevice {
  index: number;
  name: string;
  channels: number;
  default: boolean;
}

export interface VoiceDevices {
  sound_available: boolean;
  available: boolean;
  devices: VoiceDevice[];
}

export interface SystemSnapshot {
  available: boolean;
  reason?: string;
  cpu?: { percent: number; count: number };
  memory?: { total: number; used: number; percent: number };
  disks?: { mount: string; total: number; used: number; percent: number }[];
  battery?: { percent: number; plugged: boolean } | null;
  nova?: { rss: number; children: number };
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
  provider?: Record<string, unknown>;
  network?: Record<string, unknown>;
  pricing?: Record<string, unknown>;
  tools?: string[];
  budget?: Record<string, unknown>;
  warnings: string[];
  core?: Record<string, unknown>;
}

export interface BudgetStatus {
  allowed: boolean;
  reason: string;
  today_usd: number;
  month_usd: number;
  daily_limit: number;
  monthly_limit: number;
  hard_stop: boolean;
  requests_today: number;
  tokens_today: number;
  unknown_cost_today: number;
}

export interface ToolCallView {
  name: string;
  args: Record<string, unknown>;
  status: string;
  detail: string;
  ms: number;
}

export interface UsageInfo {
  inputTokens: number;
  outputTokens: number;
  thoughtsTokens: number;
  costUsd: number | null;
  costKnown: boolean;
  tier: string;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  model?: string;
  tier?: string;
  reason?: string;
  streaming?: boolean;
  error?: boolean;
  errorKind?: string;
  local?: boolean;
  tools?: ToolCallView[];
  usage?: UsageInfo;
}

export interface ConnectionTest {
  ok: boolean;
  model: string;
  latency_ms: number;
  detail: string;
}
