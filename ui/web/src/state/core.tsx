import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';

import * as api from '../lib/api';
import type {
  ChatMessage,
  ConnectionState,
  Diagnostics,
  OrbState,
  PanelId,
  SecretStatus,
  Settings,
  ThemeName,
} from '../lib/types';

interface CoreValue {
  connection: ConnectionState;
  settings: Settings | null;
  secrets: Record<string, SecretStatus> | null;
  keyringAvailable: boolean;
  diagnostics: Diagnostics | null;
  messages: ChatMessage[];
  orbState: OrbState;
  panel: PanelId;
  theme: ThemeName;
  accent: string;
  resolvedAccent: string;
  performance: boolean;
  reduceMotion: boolean;
  setPanel: (panel: PanelId) => void;
  setTheme: (theme: ThemeName) => void;
  setCustomAccent: (accent: string) => void;
  setPerformance: (value: boolean) => void;
  setReduceMotion: (value: boolean) => void;
  setOrbState: (state: OrbState) => void;
  sendMessage: (text: string) => void;
  clearChat: () => void;
  refreshDiagnostics: () => void;
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
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [orbState, setOrbState] = useState<OrbState>('idle');
  const [panel, setPanel] = useState<PanelId>(api.INITIAL_PANEL ?? 'home');
  const [theme, setThemeState] = useState<ThemeName>(api.INITIAL_THEME ?? 'cyan');
  const [accent, setAccentState] = useState('');
  const [performance, setPerformanceState] = useState(false);
  const [reduceMotion, setReduceMotionState] = useState(false);
  const [resolvedAccent, setResolvedAccent] = useState('#22d3ee');

  const socketRef = useRef<WebSocket | null>(null);
  const reconnectRef = useRef<number | null>(null);
  const forcedTheme = useRef(Boolean(api.INITIAL_THEME));

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

  // Initial load: settings, secret status, and tell the shell the UI is up.
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const [loadedSettings, loadedSecrets] = await Promise.all([
          api.getSettings(),
          api.getSecrets(),
        ]);
        if (cancelled) return;
        setSettings(loadedSettings);
        setSecrets(loadedSecrets.secrets);
        setKeyringAvailable(loadedSecrets.keyring_available);
        if (!forcedTheme.current) {
          setThemeState(loadedSettings.ui.theme);
          setAccentState(loadedSettings.ui.accent);
          setPerformanceState(loadedSettings.ui.performance_mode);
          setReduceMotionState(loadedSettings.ui.reduce_motion);
        }
      } catch {
        // Connection badge reflects the failure; defaults stay in place.
      }
    })();
    api.notifyReady();
    return () => {
      cancelled = true;
    };
  }, []);

  // WebSocket session with reconnect.
  useEffect(() => {
    let disposed = false;
    let attempts = 0;

    const handle = (payload: Envelope) => {
      const data = payload.data;
      switch (payload.type) {
        case 'hello':
          if (data?.settings) setSettings(data.settings as Settings);
          break;
        case 'orb.state':
          if (data?.state) setOrbState(data.state as OrbState);
          break;
        case 'chat.start':
          setMessages((prev) =>
            [
              ...prev,
              {
                id: String(data.id),
                role: 'assistant' as const,
                text: '',
                model: data.model,
                streaming: true,
              },
            ].slice(-MAX_MESSAGES),
          );
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
        case 'chat.done':
          setMessages((prev) =>
            prev.map((message) =>
              message.id === data.id
                ? { ...message, streaming: false, model: data.model ?? message.model }
                : message,
            ),
          );
          break;
        case 'chat.error':
        case 'error':
          setMessages((prev) =>
            [
              ...prev,
              {
                id: `err-${Date.now()}`,
                role: 'assistant' as const,
                text: String(data?.message ?? 'Something went wrong.'),
                error: true,
              },
            ].slice(-MAX_MESSAGES),
          );
          break;
        case 'settings':
          setSettings(data as Settings);
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
  }, []);

  const persist = useCallback(async (patch: unknown) => {
    try {
      setSettings(await api.putSettings(patch));
    } catch {
      /* keep local state; the next change will retry */
    }
  }, []);

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

  const sendMessage = useCallback((text: string) => {
    const trimmed = text.trim();
    if (!trimmed) return;
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
          },
        ].slice(-MAX_MESSAGES),
      );
      return;
    }
    setOrbState('thinking');
    socket.send(JSON.stringify({ type: 'chat.send', text: trimmed }));
  }, []);

  const clearChat = useCallback(() => setMessages([]), []);

  const refreshDiagnostics = useCallback(async () => {
    try {
      setDiagnostics(await api.getDiagnostics());
    } catch {
      /* ignore */
    }
  }, []);

  const value = useMemo<CoreValue>(
    () => ({
      connection,
      settings,
      secrets,
      keyringAvailable,
      diagnostics,
      messages,
      orbState,
      panel,
      theme,
      accent,
      resolvedAccent,
      performance,
      reduceMotion,
      setPanel,
      setTheme,
      setCustomAccent,
      setPerformance,
      setReduceMotion,
      setOrbState,
      sendMessage,
      clearChat,
      refreshDiagnostics,
    }),
    [
      connection,
      settings,
      secrets,
      keyringAvailable,
      diagnostics,
      messages,
      orbState,
      panel,
      theme,
      accent,
      resolvedAccent,
      performance,
      reduceMotion,
      setTheme,
      setCustomAccent,
      setPerformance,
      setReduceMotion,
      sendMessage,
      clearChat,
      refreshDiagnostics,
    ],
  );

  return <CoreContext.Provider value={value}>{children}</CoreContext.Provider>;
}
