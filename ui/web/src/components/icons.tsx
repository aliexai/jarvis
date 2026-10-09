import type { ReactElement } from 'react';

export interface IconProps {
  className?: string;
}

const panel = {
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.6,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
};

export function HomeIcon({ className }: IconProps): ReactElement {
  return (
    <svg className={className} {...panel}>
      <path d="M3 10.6 12 3.2l9 7.4" />
      <path d="M5.6 9.6V20.5h12.8V9.6" />
      <path d="M9.9 20.5v-5.2h4.2v5.2" />
    </svg>
  );
}

export function ChatIcon({ className }: IconProps): ReactElement {
  return (
    <svg className={className} {...panel}>
      <path d="M20.5 12.2c0 4-3.8 7.2-8.5 7.2-1 0-2-.15-2.9-.42L4.5 20.5l1.3-3.3A6.9 6.9 0 0 1 3.5 12.2C3.5 8.2 7.3 5 12 5s8.5 3.2 8.5 7.2Z" />
      <path d="M8.5 12h.01M12 12h.01M15.5 12h.01" />
    </svg>
  );
}

export function AgentsIcon({ className }: IconProps): ReactElement {
  return (
    <svg className={className} {...panel}>
      <circle cx="9" cy="8.5" r="3" />
      <path d="M3.6 19.5c0-3 2.4-5.2 5.4-5.2s5.4 2.2 5.4 5.2" />
      <path d="M16.2 6.2a3 3 0 0 1 0 5.6" />
      <path d="M17.4 14.6c2.1.6 3.5 2.3 3.5 4.9" />
    </svg>
  );
}

export function TasksIcon({ className }: IconProps): ReactElement {
  return (
    <svg className={className} {...panel}>
      <path d="M9.5 6.5h10M9.5 12h10M9.5 17.5h10" />
      <path d="M4.2 6.4l1.3 1.3 2.2-2.4" />
      <path d="M4.2 11.9l1.3 1.3 2.2-2.4" />
      <path d="M4.2 17.4l1.3 1.3 2.2-2.4" />
    </svg>
  );
}

export function CodingIcon({ className }: IconProps): ReactElement {
  return (
    <svg className={className} {...panel}>
      <path d="M8.5 8 4.5 12l4 4" />
      <path d="M15.5 8l4 4-4 4" />
      <path d="M13.2 5.5 10.8 18.5" />
    </svg>
  );
}

export function MemoryIcon({ className }: IconProps): ReactElement {
  return (
    <svg className={className} {...panel}>
      <ellipse cx="12" cy="6.4" rx="7" ry="2.9" />
      <path d="M5 6.4v11.2c0 1.6 3.1 2.9 7 2.9s7-1.3 7-2.9V6.4" />
      <path d="M5 12c0 1.6 3.1 2.9 7 2.9s7-1.3 7-2.9" />
    </svg>
  );
}

export function WorldIcon({ className }: IconProps): ReactElement {
  return (
    <svg className={className} {...panel}>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M3.5 12h17" />
      <path d="M12 3.5c2.4 2.4 3.6 5.3 3.6 8.5S14.4 18.1 12 20.5c-2.4-2.4-3.6-5.3-3.6-8.5S9.6 5.9 12 3.5Z" />
    </svg>
  );
}

export function SystemIcon({ className }: IconProps): ReactElement {
  return (
    <svg className={className} {...panel}>
      <rect x="7.5" y="7.5" width="9" height="9" rx="1.6" />
      <path d="M10 3.5v4M14 3.5v4M10 16.5v4M14 16.5v4M3.5 10h4M3.5 14h4M16.5 10h4M16.5 14h4" />
    </svg>
  );
}

export function SettingsIcon({ className }: IconProps): ReactElement {
  return (
    <svg className={className} {...panel}>
      <path d="M4 7.5h10M18 7.5h2M4 16.5h2M10 16.5h10" />
      <circle cx="16" cy="7.5" r="2.1" />
      <circle cx="8" cy="16.5" r="2.1" />
    </svg>
  );
}

const chrome = {
  viewBox: '0 0 12 12',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.2,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
};

export function MinimizeIcon(): ReactElement {
  return (
    <svg {...chrome}>
      <path d="M2 6h8" />
    </svg>
  );
}

export function MaximizeIcon(): ReactElement {
  return (
    <svg {...chrome}>
      <rect x="2.2" y="2.2" width="7.6" height="7.6" rx="1" />
    </svg>
  );
}

export function RestoreIcon(): ReactElement {
  return (
    <svg {...chrome}>
      <rect x="2" y="3.6" width="6.4" height="6.4" rx="1" />
      <path d="M4.4 3.6V2.4h5.2v5.2H8.4" />
    </svg>
  );
}

export function CloseIcon(): ReactElement {
  return (
    <svg {...chrome}>
      <path d="M2.6 2.6l6.8 6.8M9.4 2.6 2.6 9.4" />
    </svg>
  );
}

export function CopyIcon({ className }: IconProps): ReactElement {
  return (
    <svg className={className} {...panel}>
      <rect x="9" y="9" width="11" height="11" rx="2" />
      <path d="M15 5.5A1.5 1.5 0 0 0 13.5 4h-8A1.5 1.5 0 0 0 4 5.5v8A1.5 1.5 0 0 0 5.5 15" />
    </svg>
  );
}

export function SendIcon({ className }: IconProps): ReactElement {
  return (
    <svg className={className} {...panel}>
      <path d="M4 11.5 20 4l-7.2 16-2.1-7.2L4 11.5Z" />
    </svg>
  );
}
