import type { ReactElement } from 'react';

export function Placeholder({
  title,
  phase,
  text,
  Icon,
}: {
  title: string;
  phase: number;
  text: string;
  Icon: (props: { className?: string }) => ReactElement;
}) {
  return (
    <section className="panel">
      <header className="panel__head">
        <h1 className="panel__title">{title}</h1>
        <span className="panel__sub">Coming in Phase {phase}</span>
      </header>
      <div className="placeholder">
        <div className="placeholder__inner">
          <Icon className="placeholder__icon" />
          <span className="pill pill--ok">Phase {phase}</span>
          <h2 className="placeholder__title">{title}</h2>
          <p className="placeholder__text">{text}</p>
        </div>
      </div>
    </section>
  );
}
