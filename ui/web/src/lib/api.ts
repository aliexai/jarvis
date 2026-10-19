import type {
  BrainStatus,
  BudgetStatus,
  ConnectionTest,
  Diagnostics,
  PanelId,
  SecretsResponse,
  SecretStatus,
  Settings,
  ThemeName,
  VoiceDevices,
} from './types';

const params = new URLSearchParams(window.location.search);

/** Per-session token injected into the page URL by the Qt shell. */
export const TOKEN = params.get('token') ?? '';
export const INITIAL_PANEL = (params.get('panel') as PanelId | null) ?? null;
export const INITIAL_THEME = (params.get('theme') as ThemeName | null) ?? null;
/** Optional message sent automatically once connected (demo/screenshot helper). */
export const SEED = params.get('seed') ?? '';
/** Optional initial scroll offset for the opened panel (demo/screenshot helper). */
export const SCROLL = Number(params.get('scroll') ?? '0') || 0;

function withToken(path: string): string {
  const url = new URL(path, window.location.origin);
  url.searchParams.set('token', TOKEN);
  return url.toString();
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(withToken(path), {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return (await response.json()) as T;
}

export function getSettings(): Promise<Settings> {
  return request<Settings>('/api/settings');
}

export function putSettings(patch: unknown): Promise<Settings> {
  return request<Settings>('/api/settings', {
    method: 'PUT',
    body: JSON.stringify(patch),
  });
}

export function getSecrets(): Promise<SecretsResponse> {
  return request<SecretsResponse>('/api/secrets');
}

export function getBrain(): Promise<BrainStatus> {
  return request<BrainStatus>('/api/brain');
}

export function getVoiceDevices(): Promise<VoiceDevices> {
  return request<VoiceDevices>('/api/voice/devices');
}

export interface SecretWriteResult {
  secrets: Record<string, SecretStatus>;
  brain: BrainStatus;
  settings: Settings;
}

export function setSecret(name: string, value: string): Promise<SecretWriteResult> {
  return request<SecretWriteResult>('/api/secrets', {
    method: 'POST',
    body: JSON.stringify({ name, value }),
  });
}

export function deleteSecret(
  name: string,
): Promise<{ secrets: Record<string, SecretStatus>; brain: BrainStatus }> {
  return request(`/api/secrets/${encodeURIComponent(name)}`, { method: 'DELETE' });
}

export function getDiagnostics(): Promise<Diagnostics> {
  return request<Diagnostics>('/api/diagnostics');
}

export function getUsage(): Promise<{
  budget: BudgetStatus;
  recent: Record<string, unknown>[];
  pricing: Record<string, unknown>;
}> {
  return request('/api/usage');
}

export function testConnection(model?: string): Promise<ConnectionTest> {
  const query = model ? `?model=${encodeURIComponent(model)}` : '';
  return request<ConnectionTest>(`/api/provider/test${query}`, { method: 'POST' });
}

export function acknowledgePrivacy(): Promise<Settings> {
  return request<Settings>('/api/privacy/acknowledge', { method: 'POST' });
}

export function windowAction(action: string): void {
  void request(`/api/window/${action}`, { method: 'POST' }).catch(() => undefined);
}

export function notifyReady(): void {
  void request('/api/ui/ready', { method: 'POST' }).catch(() => undefined);
}

export function openSocket(): WebSocket {
  const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws';
  const url = `${scheme}://${window.location.host}/ws?token=${encodeURIComponent(TOKEN)}`;
  return new WebSocket(url);
}
