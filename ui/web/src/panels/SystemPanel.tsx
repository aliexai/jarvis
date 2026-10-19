import { useEffect, useState } from 'react';

import { getSystem } from '../lib/api';
import type { SystemSnapshot } from '../lib/types';

function bytes(value: number): string {
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let size = value;
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024;
    unit += 1;
  }
  return `${size.toFixed(unit === 0 || size >= 10 ? 0 : 1)} ${units[unit]}`;
}

function Gauge({ label, percent, detail }: { label: string; percent: number; detail: string }) {
  const clamped = Math.min(100, Math.max(0, percent));
  return (
    <div className="gauge">
      <div className="gauge__head">
        <span className="gauge__label">{label}</span>
        <span className="gauge__value">{Math.round(clamped)}%</span>
      </div>
      <div className="gauge__bar">
        <div
          className={`gauge__fill ${clamped >= 85 ? 'gauge__fill--hot' : ''}`}
          style={{ width: `${clamped}%` }}
        />
      </div>
      <span className="gauge__detail">{detail}</span>
    </div>
  );
}

export function SystemPanel() {
  const [snapshot, setSnapshot] = useState<SystemSnapshot | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const next = await getSystem();
        if (active) {
          setSnapshot(next);
          setError(false);
        }
      } catch {
        if (active) setError(true);
      }
    };
    void load();
    const timer = window.setInterval(load, 2000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);

  return (
    <section className="panel">
      <header className="panel__head">
        <h1 className="panel__title">System</h1>
        <span className="panel__sub">live CPU, memory, disk and NOVA&rsquo;s own usage</span>
      </header>

      <div className="settings">
        {!snapshot ? (
          <p className="row__hint">
            {error ? 'Could not read system metrics.' : 'Reading system metrics…'}
          </p>
        ) : !snapshot.available ? (
          <p className="row__hint">{snapshot.reason ?? 'System metrics are unavailable.'}</p>
        ) : (
          <>
            <div className="section">
              <h2 className="section__title">Overview</h2>
              <div className="gauges">
                {snapshot.cpu ? (
                  <Gauge
                    label="CPU"
                    percent={snapshot.cpu.percent}
                    detail={`${snapshot.cpu.count} logical cores`}
                  />
                ) : null}
                {snapshot.memory ? (
                  <Gauge
                    label="Memory"
                    percent={snapshot.memory.percent}
                    detail={`${bytes(snapshot.memory.used)} / ${bytes(snapshot.memory.total)}`}
                  />
                ) : null}
              </div>
            </div>

            <div className="section">
              <h2 className="section__title">Storage</h2>
              <div className="gauges">
                {(snapshot.disks ?? []).map((disk) => (
                  <Gauge
                    key={disk.mount}
                    label={disk.mount}
                    percent={disk.percent}
                    detail={`${bytes(disk.used)} / ${bytes(disk.total)}`}
                  />
                ))}
              </div>
            </div>

            <div className="section">
              <h2 className="section__title">Power &amp; NOVA</h2>
              <div className="row">
                <div className="row__label">
                  <span>Battery</span>
                  <span className="row__hint">
                    {snapshot.battery
                      ? snapshot.battery.plugged
                        ? 'plugged in'
                        : 'on battery'
                      : 'no battery detected'}
                  </span>
                </div>
                <span className="mono">
                  {snapshot.battery ? `${snapshot.battery.percent}%` : '—'}
                </span>
              </div>
              <div className="row">
                <div className="row__label">
                  <span>NOVA memory</span>
                  <span className="row__hint">
                    {snapshot.nova?.children ?? 0} child process(es)
                  </span>
                </div>
                <span className="mono">{snapshot.nova ? bytes(snapshot.nova.rss) : '—'}</span>
              </div>
            </div>
          </>
        )}
      </div>
    </section>
  );
}
