import { useEffect, useRef } from 'react';

import { SCROLL } from '../lib/api';
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

export function SettingsPanel() {
  const {
    settings,
    secrets,
    keyringAvailable,
    diagnostics,
    refreshDiagnostics,
    theme,
    accent,
    setTheme,
    setCustomAccent,
    performance,
    setPerformance,
    reduceMotion,
    setReduceMotion,
  } = useCore();

  const secretEntries = Object.entries(secrets ?? {});
  const scrollerRef = useRef<HTMLDivElement | null>(null);

  // Populate the diagnostics view as soon as the panel is opened.
  useEffect(() => {
    if (!diagnostics) {
      void refreshDiagnostics();
    }
  }, [diagnostics, refreshDiagnostics]);

  // Re-apply the demo scroll once async content (secrets, diagnostics) lands,
  // otherwise the container is still short and the request is clamped away.
  useEffect(() => {
    if (SCROLL <= 0) return;
    const element = scrollerRef.current;
    if (!element) return;
    const handle = window.requestAnimationFrame(() => {
      element.scrollTop = SCROLL;
    });
    return () => window.cancelAnimationFrame(handle);
  }, [diagnostics, secrets]);

  return (
    <section className="panel">
      <header className="panel__head">
        <h1 className="panel__title">Settings</h1>
        <span className="panel__sub">appearance, keys and diagnostics</span>
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
              <span className="row__hint">
                Overrides the theme accent. Reset by choosing a theme again.
              </span>
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
              <span className="row__hint">
                Fewer particles, no blur or texture, static globe later.
              </span>
            </div>
            <Toggle checked={performance} onChange={setPerformance} label="Performance mode" />
          </div>

          <div className="row">
            <div className="row__label">
              <span>Reduce motion</span>
              <span className="row__hint">Stops the orb animation and all transitions.</span>
            </div>
            <Toggle checked={reduceMotion} onChange={setReduceMotion} label="Reduce motion" />
          </div>
        </div>

        <div className="section">
          <h2 className="section__title">API keys</h2>
          <div className="row">
            <div className="row__label">
              <span>Credential manager</span>
              <span className="row__hint">
                Values are read from Credential Manager, then .env, then the environment.
              </span>
            </div>
            <span className={`pill ${keyringAvailable ? 'pill--ok' : 'pill--warn'}`}>
              {keyringAvailable ? 'available' : 'unavailable'}
            </span>
          </div>

          {secretEntries.length === 0 ? (
            <div className="row">
              <div className="row__label">
                <span>No secret status available</span>
                <span className="row__hint">The core is not reachable.</span>
              </div>
            </div>
          ) : (
            secretEntries.map(([name, status]) => (
              <div className="row" key={name}>
                <div className="row__label">
                  <span className="mono">{name}</span>
                  <span className="row__hint">source: {status.source}</span>
                </div>
                <div style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'center' }}>
                  {!status.prefix_ok ? (
                    <span className="pill pill--warn">prefix mismatch</span>
                  ) : null}
                  <span className="pill">{status.masked}</span>
                </div>
              </div>
            ))
          )}
          <p className="row__hint">
            Key values are never displayed. A mismatch warning means the value’s public prefix
            does not match the provider (for example an OpenRouter key in a Gemini slot).
          </p>
        </div>

        <div className="section">
          <h2 className="section__title">Models</h2>
          <div className="row">
            <div className="row__label">
              <span>Fast / strong</span>
              <span className="row__hint">Routing: {settings?.models.routing ?? 'auto'}</span>
            </div>
            <span className="mono">
              {settings ? `${settings.models.fast} · ${settings.models.strong}` : '—'}
            </span>
          </div>
          <div className="row">
            <div className="row__label">
              <span>Security allowlists</span>
              <span className="row__hint">folders · apps · domains · commands</span>
            </div>
            <span className="mono">
              {settings
                ? [
                    settings.security.allowed_folders.length,
                    settings.security.allowed_apps.length,
                    settings.security.allowed_domains.length,
                    settings.security.allowed_commands.length,
                  ].join(' · ')
                : '—'}
            </span>
          </div>
        </div>

        <div className="section">
          <h2 className="section__title">Diagnostics</h2>
          <div className="row">
            <div className="row__label">
              <span>Environment report</span>
              <span className="row__hint">Paths, settings, secret sources — never key values.</span>
            </div>
            <button type="button" className="btn" onClick={() => void refreshDiagnostics()}>
              Run
            </button>
          </div>
          <pre className="diag">
            {diagnostics ? JSON.stringify(diagnostics, null, 2) : 'Press “Run” to collect diagnostics.'}
          </pre>
        </div>
      </div>
    </section>
  );
}
