import { useEffect, useState } from 'react';
import type { MouseEvent as ReactMouseEvent } from 'react';

import { windowAction } from '../lib/api';
import { useCore } from '../state/core';
import { CloseIcon, MaximizeIcon, MinimizeIcon, RestoreIcon } from './icons';

declare global {
  interface Window {
    __novaWindowState?: (maximized: boolean) => void;
  }
}

export function TitleBar() {
  const { connection, settings } = useCore();
  const [maximized, setMaximized] = useState(false);

  useEffect(() => {
    window.__novaWindowState = (value: boolean) => setMaximized(value);
    return () => {
      delete window.__novaWindowState;
    };
  }, []);

  const startDrag = (event: ReactMouseEvent): void => {
    if (event.button === 0) {
      windowAction('start-move');
    }
  };

  const stop = (event: ReactMouseEvent): void => event.stopPropagation();

  return (
    <header
      className="titlebar"
      onMouseDown={startDrag}
      onDoubleClick={() => windowAction('toggle-maximize')}
    >
      <div className="titlebar__brand">
        <span className="brand-mark" />
        NOVA
      </div>
      <span className="titlebar__sub">COMMAND CENTER</span>

      <div className="titlebar__spacer" />

      <div className="titlebar__status">
        <span className={`dot ${connection === 'open' ? 'dot--live' : ''}`} />
        <span className="pill">{connection === 'open' ? 'CORE ONLINE' : connection}</span>
        {settings ? <span className="pill">{settings.models.fast}</span> : null}
      </div>

      <div
        className="titlebar__buttons"
        onMouseDown={stop}
        onDoubleClick={stop}
      >
        <button
          className="titlebar__btn"
          aria-label="Minimize"
          onClick={() => windowAction('minimize')}
        >
          <MinimizeIcon />
        </button>
        <button
          className="titlebar__btn"
          aria-label={maximized ? 'Restore' : 'Maximize'}
          onClick={() => windowAction('toggle-maximize')}
        >
          {maximized ? <RestoreIcon /> : <MaximizeIcon />}
        </button>
        <button
          className="titlebar__btn titlebar__btn--close"
          aria-label="Close"
          onClick={() => windowAction('close')}
        >
          <CloseIcon />
        </button>
      </div>
    </header>
  );
}
