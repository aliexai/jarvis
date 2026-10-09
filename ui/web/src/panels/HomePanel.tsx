import { useState } from 'react';

import { Orb } from '../components/Orb';
import { useCore } from '../state/core';
import type { OrbState } from '../lib/types';

const STATES: OrbState[] = ['idle', 'listening', 'thinking', 'speaking', 'error'];

export function HomePanel() {
  const { orbState, setOrbState, resolvedAccent, performance, reduceMotion, messages } = useCore();
  const [handsFree, setHandsFree] = useState(false);

  const toggleHandsFree = () => {
    const next = !handsFree;
    setHandsFree(next);
    setOrbState(next ? 'listening' : 'idle');
  };

  const recent = messages.slice(-6);

  return (
    <section className="panel">
      <header className="panel__head">
        <h1 className="panel__title">Voice Core</h1>
        <span className="panel__sub">
          detection of the real microphone level arrives in Phase 4
        </span>
      </header>

      <div className="home">
        <div className="home__main">
          <Orb
            state={orbState}
            accent={resolvedAccent}
            performance={performance}
            reduceMotion={reduceMotion}
          />
        </div>

        <div className="home__footer">
          <div className="home__controls">
            <button
              type="button"
              className={`btn ${handsFree ? 'btn--danger' : 'btn--primary'}`}
              onClick={toggleHandsFree}
            >
              {handsFree ? 'Stop' : 'Start'}
            </button>
            {STATES.map((candidate) => (
              <button
                key={candidate}
                type="button"
                className={`state-chip ${orbState === candidate ? 'state-chip--active' : ''}`}
                onClick={() => setOrbState(candidate)}
                title="Debug control (Phase 4 wires this to the real pipeline)"
              >
                {candidate}
              </button>
            ))}
          </div>

          <div className="glass home__transcript">
            {recent.length === 0 ? (
              <div className="line">
                <span className="line__role">Nova</span>
                <span className="line__text">
                  Standing by. Press Start, or open Chat and type a message.
                </span>
              </div>
            ) : (
              recent.map((message) => (
                <div className="line" key={message.id}>
                  <span className="line__role">
                    {message.role === 'user' ? 'You' : 'Nova'}
                  </span>
                  <span className="line__text">
                    {message.text.slice(0, 400) || '…'}
                  </span>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
