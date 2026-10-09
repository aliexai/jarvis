import type { ReactElement } from 'react';

import { useCore } from '../state/core';
import type { PanelId } from '../lib/types';
import {
  AgentsIcon,
  ChatIcon,
  CodingIcon,
  HomeIcon,
  MemoryIcon,
  SettingsIcon,
  SystemIcon,
  TasksIcon,
  WorldIcon,
} from './icons';

export interface NavEntry {
  id: PanelId;
  label: string;
  Icon: (props: { className?: string }) => ReactElement;
}

export const NAV_ITEMS: NavEntry[] = [
  { id: 'home', label: 'Home', Icon: HomeIcon },
  { id: 'chat', label: 'Chat', Icon: ChatIcon },
  { id: 'agent-town', label: 'Agents', Icon: AgentsIcon },
  { id: 'tasks', label: 'Tasks', Icon: TasksIcon },
  { id: 'coding', label: 'Coding', Icon: CodingIcon },
  { id: 'memory', label: 'Memory', Icon: MemoryIcon },
  { id: 'world-monitor', label: 'World', Icon: WorldIcon },
  { id: 'system', label: 'System', Icon: SystemIcon },
  { id: 'settings', label: 'Settings', Icon: SettingsIcon },
];

export function NavRail() {
  const { panel, setPanel, connection } = useCore();

  return (
    <nav className="nav" aria-label="Panels">
      {NAV_ITEMS.map(({ id, label, Icon }) => (
        <button
          key={id}
          type="button"
          className={`nav__item ${panel === id ? 'nav__item--active' : ''}`}
          onClick={() => setPanel(id)}
          title={label}
          aria-current={panel === id ? 'page' : undefined}
        >
          <Icon className="nav__icon" />
          <span className="nav__label">{label}</span>
        </button>
      ))}
      <div className="nav__spacer" />
      <div className="nav__foot">{connection === 'open' ? 'LINK OK' : 'OFFLINE'}</div>
    </nav>
  );
}
