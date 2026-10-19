import { useState } from 'react';

import { useCore } from '../state/core';

/** First-run prompt shown when chat has no way to reach a model. */
export function BrainOnboarding() {
  const { saveKey, enableDemo, runConnectionTest } = useCore();
  const [key, setKey] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);

  const connect = async (): Promise<void> => {
    const value = key.trim();
    if (!value) return;
    setBusy(true);
    setError(null);
    setOk(null);
    try {
      await saveKey(value);
      const test = await runConnectionTest();
      if (test.ok) {
        setOk(`Connected — ${test.model} replied in ${test.latency_ms} ms.`);
        setKey('');
      } else {
        setError(test.detail || 'The key was stored, but the test failed.');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not store the key.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="onboard glass">
      <div className="onboard__head">
        <span className="pill pill--warn">no brain connected</span>
        <h2 className="onboard__title">Connect a brain</h2>
        <p className="onboard__text">
          NOVA needs a model to answer. Paste a Google Gemini API key to go fully live,
          or explore the interface with demo replies — canned text, no network, no cost.
        </p>
      </div>

      <div className="onboard__key">
        <input
          className="input onboard__input"
          type="password"
          value={key}
          placeholder="AIza…"
          onChange={(event) => setKey(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') void connect();
          }}
          aria-label="Gemini API key"
          autoComplete="off"
          spellCheck={false}
        />
        <button
          type="button"
          className="btn btn--primary"
          onClick={() => void connect()}
          disabled={busy || !key.trim()}
        >
          {busy ? 'Connecting…' : 'Connect'}
        </button>
      </div>

      <div className="onboard__row">
        <a
          className="onboard__link"
          href="https://aistudio.google.com/apikey"
          target="_blank"
          rel="noreferrer"
        >
          aistudio.google.com/apikey ↗
        </a>
        <button
          type="button"
          className="btn btn--ghost"
          onClick={() => void enableDemo()}
          disabled={busy}
        >
          Use demo mode
        </button>
      </div>

      {ok ? <p className="onboard__ok">{ok}</p> : null}
      {error ? <p className="onboard__error">{error}</p> : null}
    </div>
  );
}
