import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';

import * as api from '../lib/api';
import type {
  BrainStatus,
  BudgetStatus,
  ChatMessage,
  ConnectionState,
  ConnectionTest,
  Diagnostics,
  OrbState,
  PanelId,
  SecretStatus,
  Settings,
  ThemeName,
  ToolCallView,
  VoiceState,
} from '../lib/types';

const GEMINI_KEY_NAME = 'NOVA_GEMINI_API_KEY';

function voiceOrbState(state: VoiceState): OrbState {
  if (state === 'transcribing') return 'thinking';
  if (state === 'error') return 'error';
  return state as OrbState;
}

interface CoreValue {
  connection: ConnectionState;
  settings: Settings | null;
  secrets: Record<string, SecretStatus> | null;
  keyringAvailable: boolean;
  diagnostics: Diagnostics | null;
  budget: BudgetStatus | null;
  brain: BrainStatus | null;
  tools: string[];
  pricing: { tier: string; last_checked: string; source: string } | null;
  messages: ChatMessage[];
  streaming: boolean;
  orbState: OrbState;
  voiceState: VoiceState;
  voiceLevel: number;
  voiceTranscript: string;
  voiceActive: boolean;
  startVoice: () => void;
  stopVoice: () => void;
  panel: PanelId;
  theme: ThemeName;
  accent: string;
  resolvedAccent: string;
  performance: boolean;
  reduceMotion: boolean;
  conversationId: string | null;
  setPanel: (panel: PanelId) => void;
  setTheme: (theme: ThemeName) => void;
  setCustomAccent: (accent: string) => void;
  setPerformance: (value: boolean) => void;
  setReduceMotion: (value: boolean) => void;
  setOrbState: (state: OrbState) => void;
  updateSettings: (patch: unknown) => Promise<void>;
  sendMessage: (text: string, modelOverride?: string) => void;
  cancelStream: () => void;
  clearChat: () => void;
  refreshDiagnostics: () => void;
  refreshUsage: () => void;
  saveKey: (value: string) => Promise<void>;
  removeKey: () => Promise<void>;
  enableDemo: () => Promise<void>;
  runConnectionTest: (model?: string) => Promise<ConnectionTest>;
  acknowledgePrivacy: () => Promise<void>;
}

const CoreContext = createContext<CoreValue | null>(null);

const MAX_MESSAGES = 250;

interface Envelope {
  type?: string;
  data?: any;
}

export function useCore(): CoreValue {
  const value = useContext(CoreContext);
  if (!value) {
    throw new Error('useCore must be used within <CoreProvider>');
  }
  return value;
}

export function CoreProvider({ children }: { children: ReactNode }) {
  const [connection, setConnection] = useState<ConnectionState>('connecting');
  const [settings, setSettings] = useState<Settings | null>(null);
  const [secrets, setSecrets] = useState<Record<string, SecretStatus> | null>(null);
  const [keyringAvailable, setKeyringAvailable] = useState(false);
  const [diagnostics, setDiagnostics] = useState<Diagnostics | null>(null);
  const [budget, setBudget] = useState<BudgetStatus | null>(null);
  const [brain, setBrain] = useState<BrainStatus | null>(null);
  const [tools, setTools] = useState<string[]>([]);
  const [pricing, setPricing] = useState<CoreValue['pricing']>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [orbState, setOrbState] = useState<OrbState>('idle');
  const [voiceState, setVoiceState] = useState<VoiceState>('idle');
  const [voiceLevel, setVoiceLevel] = useState(0);
  const [voiceTranscript, setVoiceTranscript] = useState('');
  const [panel, setPanel] = useState<PanelId>(api.INITIAL_PANEL ?? 'home');
  const [theme, setThemeState] = useState<ThemeName>(api.INITIAL_THEME ?? 'cyan');
  const [accent, setAccentState] = useState('');
  const [performance, setPerformanceState] = useState(false);
  const [reduceMotion, setReduceMotionState] = useState(false);
  const [resolvedAccent, setResolvedAccent] = useState('#22d3ee');
  const [conversationId, setConversationId] = useState<string | null>(null);

  const socketRef = useRef<WebSocket | null>(null);
  const reconnectRef = useRef<number | null>(null);
  const forcedTheme = useRef(Boolean(api.INITIAL_THEME));
  const streamingRef = useRef(false);

  // Apply theme/accessibility state to the document and resolve the live accent.
  useEffect(() => {
    const root = document.documentElement;
    root.dataset.theme = theme;
    root.dataset.performance = String(performance);
    root.dataset.reduceMotion = String(reduceMotion);
    if (accent) {
      root.style.setProperty('--accent', accent);
    } else {
      root.style.removeProperty('--accent');
    }
    const computed = getComputedStyle(root).getPropertyValue('--accent').trim();
    if (computed) {
      setResolvedAccent(computed);
    }
  }, [theme, accent, performance, reduceMotion]);

  const applySettings = useCallback((next: Settings, adopt: boolean) => {
    setSettings(next);
    if (adopt && !forcedTheme.current) {
      setThemeState(next.ui.theme);
      setAccentState(next.ui.accent);
      setPerformanceState(next.ui.performance_mode);
      setReduceMotionState(next.ui.reduce_motion);
    }
  }, []);

  // Initial load: settings, secret status, and tell the shell the UI is up.
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const [loadedSettings, loadedSecrets, loadedBrain] = await Promise.all([
          api.getSettings(),
          api.getSecrets(),
          api.getBrain(),
        ]);
        if (cancelled) return;
        applySettings(loadedSettings, true);
        setSecrets(loadedSecrets.secrets);
        setKeyringAvailable(loadedSecrets.keyring_available);
        setBrain(loadedBrain);
      } catch {
        // Connection badge reflects the failure; defaults stay in place.
      }
    })();
    api.notifyReady();
    return () => {
      cancelled = true;
    };
  }, [applySettings]);

  // WebSocket session with reconnect.
  useEffect(() => {
    let disposed = false;
    let attempts = 0;

    const setStreamingBoth = (value: boolean) => {
      streamingRef.current = value;
      setStreaming(value);
    };

    const handle = (payload: Envelope) => {
      const data = payload.data;
      switch (payload.type) {
        case 'hello':
          if (data?.settings) applySettings(data.settings as Settings, false);
          if (data?.budget) setBudget(data.budget as BudgetStatus);
          if (data?.brain) setBrain(data.brain as BrainStatus);
          if (data?.tools) setTools(data.tools as string[]);
          if (data?.pricing) setPricing(data.pricing as CoreValue['pricing']);
          break;

        case 'orb.state':
          if (data?.state) setOrbState(data.state as OrbState);
          break;

        case 'voice.state': {
          const next = String(data?.state ?? 'idle') as VoiceState;
          setVoiceState(next);
          setOrbState(voiceOrbState(next));
          break;
        }

        case 'voice.level':
          setVoiceLevel(Number(data?.level ?? 0));
          break;

        case 'voice.transcript':
          setVoiceTranscript(String(data?.text ?? ''));
          break;

        case 'voice.error':
          setVoiceState('error');
          setMessages((prev) =>
            [
              ...prev,
              {
                id: `err-${Date.now()}`,
                role: 'assistant' as const,
                text: String(data?.message ?? 'Voice error.'),
                error: true,
                errorKind: String(data?.kind ?? 'voice'),
              },
            ].slice(-MAX_MESSAGES),
          );
          break;

        case 'chat.start':
          if (data?.conversation_id) setConversationId(String(data.conversation_id));
          setMessages((prev) =>
            [
              ...prev,
              {
                id: String(data.id),
                role: 'assistant' as const,
                text: '',
                model: data.model,
                tier: data.tier,
                reason: data.reason,
                streaming: true,
                tools: [],
              },
            ].slice(-MAX_MESSAGES),
          );
          setStreamingBoth(true);
          break;

        case 'chat.delta':
          setMessages((prev) =>
            prev.map((message) =>
              message.id === data.id
                ? { ...message, text: message.text + String(data.text ?? '') }
                : message,
            ),
          );
          break;

        case 'chat.tool': {
          const call: ToolCallView = {
            name: String(data.name),
            args: (data.args ?? {}) as Record<string, unknown>,
            status: String(data.status),
            detail: String(data.detail ?? ''),
            ms: Number(data.ms ?? 0),
          };
          setMessages((prev) =>
            prev.map((message) =>
              message.id === data.id
                ? { ...message, tools: [...(message.tools ?? []), call] }
                : message,
            ),
          );
          break;
        }

        case 'chat.usage':
          setMessages((prev) =>
            prev.map((message) =>
              message.id === data.id
                ? {
                    ...message,
                    usage: {
                      inputTokens: Number(data.input_tokens ?? 0),
                      outputTokens: Number(data.output_tokens ?? 0),
                      thoughtsTokens: Number(data.thoughts_tokens ?? 0),
                      costUsd: data.cost_usd === null ? null : Number(data.cost_usd),
                      costKnown: Boolean(data.cost_known),
                      tier: String(data.tier ?? ''),
                    },
                  }
                : message,
            ),
          );
          if (data.budget) setBudget(data.budget as BudgetStatus);
          break;

        case 'chat.done':
          setStreamingBoth(false);
          setMessages((prev) =>
            prev.map((message) =>
              message.id === data?.id
                ? { ...message, streaming: false }
                : data?.aborted
                  ? { ...message, streaming: false }
                  : message,
            ),
          );
          break;

        case 'chat.error':
        case 'error': {
          setStreamingBoth(false);
          const message = String(data?.message ?? 'Something went wrong.');
          const kind = String(data?.kind ?? 'error');
          setMessages((prev) => {
            const target = data?.id
              ? prev.find((item) => item.id === data.id)
              : prev.find((item) => item.streaming);
            if (target) {
              return prev.map((item) =>
                item.id === target.id
                  ? { ...item, streaming: false, error: true, errorKind: kind, text: item.text || message }
                  : item,
              );
            }
            return [
              ...prev,
              {
                id: `err-${Date.now()}`,
                role: 'assistant' as const,
                text: message,
                error: true,
                errorKind: kind,
              },
            ].slice(-MAX_MESSAGES);
          });
          break;
        }

        case 'settings':
          applySettings(data as Settings, false);
          break;

        case 'budget':
          setBudget(data as BudgetStatus);
          break;

        case 'brain':
          setBrain(data as BrainStatus);
          break;

        case 'settings.error':
          setMessages((prev) =>
            [
              ...prev,
              {
                id: `err-${Date.now()}`,
                role: 'assistant' as const,
                text: String(data?.message ?? 'Settings update failed.'),
                error: true,
                errorKind: 'settings',
              },
            ].slice(-MAX_MESSAGES),
          );
          break;

        default:
          break;
      }
    };

    const connect = () => {
      if (disposed) return;
      setConnection('connecting');
      const socket = api.openSocket();
      socketRef.current = socket;

      socket.onopen = () => {
        attempts = 0;
        setConnection('open');
      };
      socket.onmessage = (event) => {
        try {
          handle(JSON.parse(String(event.data)) as Envelope);
        } catch {
          /* ignore malformed frames */
        }
      };
      socket.onerror = () => socket.close();
      socket.onclose = () => {
        setConnection('closed');
        setStreamingBoth(false);
        if (disposed) return;
        attempts += 1;
        const delay = Math.min(5000, 400 * attempts);
        reconnectRef.current = window.setTimeout(connect, delay);
      };
    };

    connect();
    return () => {
      disposed = true;
      if (reconnectRef.current !== null) window.clearTimeout(reconnectRef.current);
      socketRef.current?.close();
    };
  }, [applySettings]);

  const persist = useCallback(
    async (patch: unknown) => {
      try {
        applySettings(await api.putSettings(patch), false);
        api.getUsage().then((usage) => setBudget(usage.budget)).catch(() => undefined);
        api.getBrain().then(setBrain).catch(() => undefined);
      } catch {
        /* keep local state; the next change will retry */
      }
    },
    [applySettings],
  );

  const saveKey = useCallback(
    async (value: string) => {
      const result = await api.setSecret(GEMINI_KEY_NAME, value.trim());
      setSecrets(result.secrets);
      setBrain(result.brain);
      applySettings(result.settings, false);
      if (result.settings.provider.name !== 'gemini') {
        await persist({ provider: { name: 'gemini' } });
      }
    },
    [applySettings, persist],
  );

  const removeKey = useCallback(async () => {
    const result = await api.deleteSecret(GEMINI_KEY_NAME);
    setSecrets(result.secrets);
    setBrain(result.brain);
  }, []);

  const enableDemo = useCallback(async () => {
    await persist({ provider: { name: 'mock' } });
  }, [persist]);

  const setTheme = useCallback(
    (next: ThemeName) => {
      setThemeState(next);
      setAccentState('');
      void persist({ ui: { theme: next, accent: '' } });
    },
    [persist],
  );

  const setCustomAccent = useCallback(
    (value: string) => {
      setAccentState(value);
      void persist({ ui: { accent: value } });
    },
    [persist],
  );

  const setPerformance = useCallback(
    (value: boolean) => {
      setPerformanceState(value);
      void persist({ ui: { performance_mode: value } });
    },
    [persist],
  );

  const setReduceMotion = useCallback(
    (value: boolean) => {
      setReduceMotionState(value);
      void persist({ ui: { reduce_motion: value } });
    },
    [persist],
  );

  const sendMessage = useCallback((text: string, modelOverride?: string) => {
    const trimmed = text.trim();
    if (!trimmed || streamingRef.current) return;
    const socket = socketRef.current;
    setMessages((prev) =>
      [...prev, { id: `u-${Date.now()}`, role: 'user' as const, text: trimmed }].slice(
        -MAX_MESSAGES,
      ),
    );
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      setMessages((prev) =>
        [
          ...prev,
          {
            id: `err-${Date.now()}`,
            role: 'assistant' as const,
            text: 'Not connected to the NOVA core.',
            error: true,
            errorKind: 'offline',
          },
        ].slice(-MAX_MESSAGES),
      );
      return;
    }
    setOrbState('thinking');
    socket.send(
      JSON.stringify({ type: 'chat.send', text: trimmed, model: modelOverride, conversation_id: conversationId }),
    );
  }, [conversationId]);

  const cancelStream = useCallback(() => {
    const socket = socketRef.current;
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: 'chat.cancel' }));
    }
  }, []);

  const startVoice = useCallback(() => {
    const socket = socketRef.current;
    if (socket && socket.readyState === WebSocket.OPEN) {
      setVoiceTranscript('');
      socket.send(JSON.stringify({ type: 'voice.start' }));
    }
  }, []);

  const stopVoice = useCallback(() => {
    const socket = socketRef.current;
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: 'voice.stop' }));
    }
  }, []);

  const clearChat = useCallback(() => {
    setMessages([]);
    setConversationId(null);
  }, []);

  const refreshDiagnostics = useCallback(async () => {
    try {
      setDiagnostics(await api.getDiagnostics());
    } catch {
      /* ignore */
    }
  }, []);

  const refreshUsage = useCallback(async () => {
    try {
      const usage = await api.getUsage();
      setBudget(usage.budget);
    } catch {
      /* ignore */
    }
  }, []);

  const runConnectionTest = useCallback((model?: string) => api.testConnection(model), []);

  const acknowledgePrivacy = useCallback(async () => {
    try {
      applySettings(await api.acknowledgePrivacy(), false);
    } catch {
      /* ignore */
    }
  }, [applySettings]);

  const updateSettings = useCallback(
    async (patch: unknown) => {
      await persist(patch);
    },
    [persist],
  );

  const value = useMemo<CoreValue>(
    () => ({
      connection,
      settings,
      secrets,
      keyringAvailable,
      diagnostics,
      budget,
      brain,
      tools,
      pricing,
      messages,
      streaming,
      orbState,
      voiceState,
      voiceLevel,
      voiceTranscript,
      voiceActive: voiceState === 'listening',
      startVoice,
      stopVoice,
      panel,
      theme,
      accent,
      resolvedAccent,
      performance,
      reduceMotion,
      conversationId,
      setPanel,
      setTheme,
      setCustomAccent,
      setPerformance,
      setReduceMotion,
      setOrbState,
      updateSettings,
      sendMessage,
      cancelStream,
      clearChat,
      refreshDiagnostics,
      refreshUsage,
      saveKey,
      removeKey,
      enableDemo,
      runConnectionTest,
      acknowledgePrivacy,
    }),
    [
      connection,
      settings,
      secrets,
      keyringAvailable,
      diagnostics,
      budget,
      brain,
      tools,
      pricing,
      messages,
      streaming,
      orbState,
      voiceState,
      voiceLevel,
      voiceTranscript,
      voiceActive: voiceState === 'listening',
      startVoice,
      stopVoice,
      panel,
      theme,
      accent,
      resolvedAccent,
      performance,
      reduceMotion,
      conversationId,
      setTheme,
      setCustomAccent,
      setPerformance,
      setReduceMotion,
      updateSettings,
      sendMessage,
      cancelStream,
      clearChat,
      refreshDiagnostics,
      refreshUsage,
      saveKey,
      removeKey,
      enableDemo,
      runConnectionTest,
      acknowledgePrivacy,
    ],
  );

  return <CoreContext.Provider value={value}>{children}</CoreContext.Provider>;
}
