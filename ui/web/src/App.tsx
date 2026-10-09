import { NavRail } from './components/NavRail';
import { PrivacyNotice } from './components/PrivacyNotice';
import { TitleBar } from './components/TitleBar';
import {
  AgentsIcon,
  CodingIcon,
  MemoryIcon,
  SystemIcon,
  TasksIcon,
  WorldIcon,
} from './components/icons';
import { ChatPanel } from './panels/ChatPanel';
import { HomePanel } from './panels/HomePanel';
import { Placeholder } from './panels/Placeholder';
import { SettingsPanel } from './panels/SettingsPanel';
import { useCore } from './state/core';
import type { PanelId } from './lib/types';

const PLACEHOLDERS: Partial<
  Record<
    PanelId,
    { title: string; phase: number; text: string; Icon: (p: { className?: string }) => JSX.Element }
  >
> = {
  'agent-town': {
    title: 'Agent Town',
    phase: 7,
    text: 'Four resident sub-agents — Operator, Coder, Researcher and Reviewer — with live status, current task and recent output, working in parallel.',
    Icon: AgentsIcon,
  },
  tasks: {
    title: 'Tasks & Tools',
    phase: 7,
    text: 'Step-by-step task progress, the tool-call timeline with arguments and durations, per-task cancel and a global emergency stop.',
    Icon: TasksIcon,
  },
  coding: {
    title: 'Coding Workspace',
    phase: 6,
    text: 'Choose a project folder, browse the file tree, review every proposed change as a diff, run the tests and roll back to a git checkpoint.',
    Icon: CodingIcon,
  },
  memory: {
    title: 'Memory / Soul',
    phase: 7,
    text: 'View, edit, search, export and delete memories, tune personality sliders and edit the system prompt.',
    Icon: MemoryIcon,
  },
  'world-monitor': {
    title: 'World Monitor',
    phase: 8,
    text: 'A 3D globe with hotspot markers, a 2D map view and a headlines feed from your editable free RSS sources.',
    Icon: WorldIcon,
  },
  system: {
    title: 'System',
    phase: 8,
    text: 'CPU, RAM, disk, battery and network gauges, running applications, and NOVA’s own resource usage.',
    Icon: SystemIcon,
  },
};

export function App() {
  const { panel } = useCore();
  const placeholder = PLACEHOLDERS[panel];

  return (
    <div className="app">
      <TitleBar />
      <div className="body">
        <NavRail />
        <main className="content">
          <PrivacyNotice />
          {panel === 'home' ? <HomePanel /> : null}
          {panel === 'chat' ? <ChatPanel /> : null}
          {panel === 'settings' ? <SettingsPanel /> : null}
          {placeholder ? <Placeholder {...placeholder} /> : null}
        </main>
      </div>
    </div>
  );
}
