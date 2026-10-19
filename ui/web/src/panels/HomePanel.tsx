import { useEffect, useState } from 'react';

import { Orb } from '../components/Orb';
import * as api from '../lib/api';
import { useCore } from '../state/core';
import type { VoiceDevices } from '../lib/types';

export function HomePanel() {
  const {
    orbState,
    resolvedAccent,
    performance,
    reduceMotion,
    messages,
    voiceState,
    voiceLevel,
    voiceTranscript,
    voiceActive,
    startVoice,
    stopVoice,
  } = useCore();
  const [devices, setDevices] = useState<VoiceDevices | null>(null);

  useEffect(() => {
    void api
      .getVoiceDevices()
      .then(setDevices)
      .catch(() => setDevices(null));
  }, []);

  const working =
    voiceState === 'transcribing' || voiceState === 'thinking' || voiceState === 'speaking';
  const recent = messages.slice(-6);
  const noMic = devices !== null && !devices.available;

  return (
    <section className="panel">
      <header className="panel__head">
        <h1 className="panel__title">Voice Core</h1>
        <span className="panel__sub">
          {devices === null
            ? 'checking the microphone…'
            : noMic
              ? 'no microphone detected'
              : `${devices.devices.length} input device${
                  devices.devices.length === 1 ? '' : 's'
                } · local speech-to-text`}
        </span>
      </header>

      <div className="home">
        <div className="home__main">
          <Orb
            state={orbState}
            accent={resolvedAccent}
            performance={performance}
            reduceMotion={reduceMotion}
            level={voiceLevel}
          />
        </div>

        <div className="home__footer">
          <div className="home__controls">
            <button
              type="button"
              className={`btn ${voiceActive || working ? 'btn--danger' : 'btn--primary'}`}
              onClick={voiceActive ? stopVoice : startVoice}
              disabled={working || noMic}
            >
              {voiceActive ? 'Stop' : working ? 'Working…' : 'Start'}
            </button>
            <span className="voice-state-pill">{voiceState}</span>
            <div className="voice-meter" aria-hidden="true">
              <div
                className="voice-meter__fill"
                style={{ width: `${Math.round(Math.min(1, voiceLevel) * 100)}%` }}
              />
            </div>
          </div>

          <div className="glass home__transcript">
            {voiceTranscript ? (
              <div className="line">
                <span className="line__role">Heard</span>
                <span className="line__text">{voiceTranscript}</span>
              </div>
            ) : null}
            {recent.length === 0 && !voiceTranscript ? (
              <div className="line">
                <span className="line__role">Nova</span>
                <span className="line__text">
                  {noMic
                    ? 'No microphone found. Open Chat to type a message instead.'
                    : 'Press Start and speak — NOVA stops listening when you pause.'}
                </span>
              </div>
            ) : (
              recent.map((message) => (
                <div className="line" key={message.id}>
                  <span className="line__role">{message.role === 'user' ? 'You' : 'Nova'}</span>
                  <span className="line__text">{message.text.slice(0, 400) || '…'}</span>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
