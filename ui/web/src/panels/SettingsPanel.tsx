import { useEffect, useRef, useState } from 'react';

import { SCROLL } from '../lib/api';
import { formatCost, formatTokens } from '../lib/format';
import { useCore } from '../state/core';
import type { ThemeName } from '../lib/types';

const THEME_META: { id: ThemeName; name: string; swatch: string }[] = [
  { id: 'cyan', name: 'Cyan', swatch: 'linear-gradient(135deg, #22d3ee, #0ea5e9)' },
  { id: 'emerald', name: 'Emerald', swatch: 'linear-gradient(135deg, #34d399, #059669)' },
  { id: 'crimson', name: 'Crimson', swatch: 'linear-gradient(135deg, #f43f5e, #be123c)' },
];

function Toggle({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (value: boolean) => void;
  label: string;
}) {
  return (
    <button
      type="button"
      className="switch"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={() => onChange(!checked)}
    />
  );
}

function TextField({
  value,
  onCommit,
  narrow = false,
  numeric = false,
  placeholder,
}: {
  value: string | number;
  onCommit: (value: string) => void;
  narrow?: boolean;
  numeric?: boolean;
  placeholder?: string;
}) {
  const [local, setLocal] = useState(String(value));

  useEffect(() => {
    setLocal(String(value));
  }, [value]);

  return (
    <input
      className={`input ${narrow ? 'input--narrow' : ''}`}
      type={numeric ? 'number' : 'text'}
      value={local}
      placeholder={placeholder}
      onChange={(event) => setLocal(event.target.value)}
      onBlur={() => {
        if (local !== String(value)) onCommit(local);
      }}
      onKeyDown={(event) => {
        if (event.key === 'Enter') (event.target as HTMLInputElement).blur();
      }}
    />
  );
}

function SelectField({
  value,
  options,
  onCommit,
}: {
  value: string;
  options: { value: string; label: string }[];
  onCommit: (value: string) => void;
}) {
  return (
    <select className="input" value={value} onChange={(event) => onCommit(event.target.value)}>
      {options.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  );
}

export function SettingsPanel() {
  const {
    settings,
    secrets,
    keyringAvailable,
    diagnostics,
    refreshDiagnostics,
    budget,
    pricing,
    tools,
    theme,
    accent,
    setTheme,
    setCustomAccent,
    performance,
    setPerformance,
    reduceMotion,
    setReduceMotion,
    updateSettings,
    runConnectionTest,
  } = useCore();

  const [testModel, setTestModel] = useState('');
  const [testResult, setTestResult] = useState<
    { ok: boolean; model: string; latency_ms: number; detail: string } | null
  >(null);
  const [testing, setTesting] = useState(false);
  const scrollerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!diagnostics) {
      void refreshDiagnostics();
    }
  }, [diagnostics, refreshDiagnostics]);

  useEffect(() => {
    if (SCROLL <= 0) return;
    const element = scrollerRef.current;
    if (!element) return;
    const handle = window.requestAnimationFrame(() => {
      element.scrollTop = SCROLL;
    });
    return () => window.cancelAnimationFrame(handle);
  }, [diagnostics, secrets]);

  const effectiveTestModel = testModel || settings?.models.fast || '';

  const onTest = async () => {
    setTesting(true);
    try {
      setTestResult(await runConnectionTest(effectiveTestModel));
    } catch {
      setTestResult({ ok: false, model: effectiveTestModel, latency_ms: 0, detail: 'request failed' });
    } finally {
      setTesting(false);
    }
  };

  const secretEntries = Object.entries(secrets ?? {});

  return (
    <section className="panel">
      <header className="panel__head">
        <h1 className="panel__title">Settings</h1>
        <span className="panel__sub">appearance, brain, network, cost and diagnostics</span>
      </header>

      <div className="settings" ref={scrollerRef}>
        <div className="section">
          <h2 className="section__title">Appearance</h2>
          <div className="themes">
            {THEME_META.map((meta) => (
              <button
                key={meta.id}
                type="button"
                className={`theme-card ${theme === meta.id ? 'theme-card--active' : ''}`}
                onClick={() => setTheme(meta.id)}
                aria-pressed={theme === meta.id}
              >
                <span className="swatch" style={{ background: meta.swatch }} />
                <span className="theme-card__name">{meta.name}</span>
              </button>
            ))}
          </div>

          <div className="row">
            <div className="row__label">
              <span>Custom accent</span>
              <span className="row__hint">Overrides the theme accent.</span>
            </div>
            <div style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'center' }}>
              <span className="mono" style={{ color: 'var(--text-faint)' }}>
                {accent || 'theme default'}
              </span>
              <input
                type="color"
                aria-label="Custom accent colour"
                value={/^#[0-9a-f]{6}$/i.test(accent) ? accent : '#22d3ee'}
                onChange={(event) => setCustomAccent(event.target.value)}
              />
            </div>
          </div>

          <div className="row">
            <div className="row__label">
              <span>Performance mode</span>
              <span className="row__hint">Fewer particles, no blur or texture.</span>
            </div>
            <Toggle checked={performance} onChange={setPerformance} label="Performance mode" />
          </div>

          <div className="row">
            <div className="row__label">
              <span>Reduce motion</span>
              <span className="row__hint">Stops orb animation and transitions.</span>
            </div>
            <Toggle checked={reduceMotion} onChange={setReduceMotion} label="Reduce motion" />
          </div>
        </div>

        <div className="section">
          <h2 className="section__title">Brain</h2>
          <div className="row">
            <div className="row__label">
              <span>Provider</span>
              <span className="row__hint">mock needs no key and never touches the network.</span>
            </div>
            <SelectField
              value={settings?.provider.name ?? 'gemini'}
              options={[
                { value: 'gemini', label: 'Gemini' },
                { value: 'mock', label: 'Mock (offline)' },
              ]}
              onCommit={(value) => void updateSettings({ provider: { name: value } })}
            />
          </div>

          <div className="row">
            <div className="row__label">
              <span>Fast model</span>
              <span className="row__hint">Used for routine, short requests.</span>
            </div>
            <TextField
              value={settings?.models.fast ?? ''}
              onCommit={(value) => void updateSettings({ models: { fast: value } })}
            />
          </div>

          <div className="row">
            <div className="row__label">
              <span>Strong model</span>
              <span className="row__hint">Used for coding, planning and long reasoning.</span>
            </div>
            <TextField
              value={settings?.models.strong ?? ''}
              onCommit={(value) => void updateSettings({ models: { strong: value } })}
            />
          </div>

          <div className="row">
            <div className="row__label">
              <span>Routing</span>
              <span className="row__hint">auto picks per message; the others force a model.</span>
            </div>
            <SelectField
              value={settings?.models.routing ?? 'auto'}
              options={[
                { value: 'auto', label: 'Auto' },
                { value: 'fast', label: 'Always fast' },
                { value: 'strong', label: 'Always strong' },
              ]}
              onCommit={(value) => void updateSettings({ models: { routing: value } })}
            />
          </div>

          <div className="row">
            <div className="row__label">
              <span>Tool calling</span>
              <span className="row__hint">
                {tools.length ? `Registered: ${tools.join(', ')}` : 'No tools registered'}
              </span>
            </div>
            <Toggle
              checked={settings?.provider.tools_enabled ?? true}
              onChange={(value) => void updateSettings({ provider: { tools_enabled: value } })}
              label="Tool calling"
            />
          </div>

          <div className="row">
            <div className="row__label">
              <span>Test connection</span>
              <span className="row__hint">
                {testing ? 'Testing…' : 'Sends one tiny request. The key is never shown.'}
              </span>
            </div>
            <div style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'center' }}>
              {testResult ? (
                <span className={`pill ${testResult.ok ? 'pill--ok' : 'pill--bad'}`}>
                  {testResult.ok ? 'OK' : 'FAILED'} · {testResult.latency_ms} ms
                </span>
              ) : null}
              <TextField value={effectiveTestModel} onCommit={setTestModel} placeholder="model id" />
              <button type="button" className="btn" onClick={() => void onTest()} disabled={testing}>
                Test
              </button>
            </div>
          </div>
          {testResult && !testResult.ok ? (
            <p className="row__hint">{testResult.detail}</p>
          ) : null}
          {testResult && testResult.ok ? (
            <p className="row__hint">Tested {testResult.model} — {testResult.detail}</p>
          ) : null}
        </div>

        <div className="section">
          <h2 className="section__title">Network</h2>
          <div className="row">
            <div className="row__label">
              <span>Proxy</span>
              <span className="row__hint">
                Windows settings are never modified. This machine advertises a SOCKS proxy, which
                the client cannot use directly.
              </span>
            </div>
            <SelectField
              value={settings?.provider.proxy_mode ?? 'bypass'}
              options={[
                { value: 'bypass', label: 'Bypass proxy' },
                { value: 'system', label: 'Use system proxy' },
                { value: 'manual', label: 'Manual' },
              ]}
              onCommit={(value) => void updateSettings({ provider: { proxy_mode: value } })}
            />
          </div>

          {settings?.provider.proxy_mode === 'manual' ? (
            <div className="row">
              <div className="row__label">
                <span>Proxy URL</span>
                <span className="row__hint">http:// or https:// only.</span>
              </div>
              <TextField
                value={settings.provider.proxy_url}
                onCommit={(value) => void updateSettings({ provider: { proxy_url: value } })}
              />
            </div>
          ) : null}

          <div className="row">
            <div className="row__label">
              <span>Timeout / retries</span>
              <span className="row__hint">Seconds, and attempts with exponential backoff.</span>
            </div>
            <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
              <TextField
                value={settings?.provider.timeout_seconds ?? 60}
                numeric
                narrow
                onCommit={(value) =>
                  void updateSettings({ provider: { timeout_seconds: Number(value) || 60 } })
                }
              />
              <TextField
                value={settings?.provider.max_retries ?? 3}
                numeric
                narrow
                onCommit={(value) =>
                  void updateSettings({ provider: { max_retries: Number(value) || 0 } })
                }
              />
            </div>
          </div>

          {diagnostics?.network ? (
            <div className="row">
              <div className="row__label">
                <span>Detected proxy</span>
                <span className="row__hint">
                  {String((diagnostics.network as Record<string, unknown>).note ?? '')}
                </span>
              </div>
              <span className="mono">
                {String((diagnostics.network as Record<string, unknown>).effective ?? 'none')}
              </span>
            </div>
          ) : null}
        </div>

        <div className="section">
          <h2 className="section__title">Cost</h2>
          <div className="row">
            <div className="row__label">
              <span>Pricing tier</span>
              <span className="row__hint">
                The free tier is free of charge; paid uses the published per-million rates.
              </span>
            </div>
            <SelectField
              value={settings?.pricing.tier ?? 'free'}
              options={[
                { value: 'free', label: 'Free tier' },
                { value: 'paid', label: 'Paid tier' },
              ]}
              onCommit={(value) => void updateSettings({ pricing: { tier: value } })}
            />
          </div>

          <div className="row">
            <div className="row__label">
              <span>Prices last checked</span>
              <span className="row__hint">{pricing?.source ?? 'official pricing page'}</span>
            </div>
            <span className="mono">{pricing?.last_checked ?? '—'}</span>
          </div>

          <div className="row">
            <div className="row__label">
              <span>Spend so far</span>
              <span className="row__hint">
                {budget ? `${budget.requests_today} requests · ${formatTokens(budget.tokens_today)} tokens` : '—'}
                {budget && budget.unknown_cost_today > 0
                  ? ` · ${budget.unknown_cost_today} request(s) with unknown price`
                  : ''}
              </span>
            </div>
            <span className="mono">
              {budget ? `${formatCost(budget.today_usd)} today · ${formatCost(budget.month_usd)} month` : '—'}
            </span>
          </div>

          <div className="row">
            <div className="row__label">
              <span>Daily limit (USD)</span>
              <span className="row__hint">Soft limit; the hard stop blocks new requests.</span>
            </div>
            <div style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'center' }}>
              <Toggle
                checked={settings?.limits.enabled ?? true}
                onChange={(value) => void updateSettings({ limits: { enabled: value } })}
                label="Limits enabled"
              />
              <TextField
                value={settings?.limits.daily_usd ?? 1}
                numeric
                narrow
                onCommit={(value) =>
                  void updateSettings({ limits: { daily_usd: Number(value) || 0 } })
                }
              />
            </div>
          </div>

          <div className="row">
            <div className="row__label">
              <span>Monthly limit (USD)</span>
              <span className="row__hint">Blocks new requests once reached.</span>
            </div>
            <TextField
              value={settings?.limits.monthly_usd ?? 10}
              numeric
              narrow
              onCommit={(value) =>
                void updateSettings({ limits: { monthly_usd: Number(value) || 0 } })
              }
            />
          </div>

          <div className="row">
            <div className="row__label">
              <span>Hard stop</span>
              <span className="row__hint">When off, limits are a warning only.</span>
            </div>
            <Toggle
              checked={settings?.limits.hard_stop ?? true}
              onChange={(value) => void updateSettings({ limits: { hard_stop: value } })}
              label="Hard stop"
            />
          </div>
        </div>

        <div className="section">
          <h2 className="section__title">Privacy</h2>
          <div className="row">
            <div className="row__label">
              <span>Free-tier notice</span>
              <span className="row__hint">
                Free-tier Gemini content may be used by Google to improve its products.
              </span>
            </div>
            <span
              className={`pill ${settings?.privacy.notice_acknowledged ? 'pill--ok' : 'pill--warn'}`}
            >
              {settings?.privacy.notice_acknowledged ? 'acknowledged' : 'pending'}
            </span>
          </div>
          <div className="row">
            <div className="row__label">
              <span>Remind before attaching</span>
              <span className="row__hint">No file contents are ever sent unless attached.</span>
            </div>
            <Toggle
              checked={settings?.privacy.remind_before_attach ?? true}
              onChange={(value) =>
                void updateSettings({ privacy: { remind_before_attach: value } })
              }
              label="Remind before attaching"
            />
          </div>
        </div>

        <div className="section">
          <h2 className="section__title">API keys</h2>
          <div className="row">
            <div className="row__label">
              <span>Credential manager</span>
              <span className="row__hint">
                Read from Credential Manager, then .env, then the environment.
              </span>
            </div>
            <span className={`pill ${keyringAvailable ? 'pill--ok' : 'pill--warn'}`}>
              {keyringAvailable ? 'available' : 'unavailable'}
            </span>
          </div>

          {secretEntries.map(([name, status]) => (
            <div className="row" key={name}>
              <div className="row__label">
                <span className="mono">{name}</span>
                <span className="row__hint">source: {status.source}</span>
              </div>
              <div style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'center' }}>
                {!status.prefix_ok ? <span className="pill pill--warn">prefix mismatch</span> : null}
                <span className="pill">{status.masked}</span>
              </div>
            </div>
          ))}
          <p className="row__hint">
            Key values are never displayed. To add or replace a key, put it in a local{' '}
            <span className="mono">.env</span> file or Windows Credential Manager.
          </p>
        </div>

        <div className="section">
          <h2 className="section__title">Diagnostics</h2>
          <div className="row">
            <div className="row__label">
              <span>Environment report</span>
              <span className="row__hint">Paths, provider, proxy, pricing — never key values.</span>
            </div>
            <button type="button" className="btn" onClick={() => void refreshDiagnostics()}>
              Run
            </button>
          </div>
          <pre className="diag">
            {diagnostics
              ? JSON.stringify(diagnostics, null, 2)
              : 'Press “Run” to collect diagnostics.'}
          </pre>
        </div>
      </div>
    </section>
  );
}
