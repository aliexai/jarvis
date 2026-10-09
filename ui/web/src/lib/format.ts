/** Formatting helpers shared by the cost meter and message footers. */

export function formatCost(value: number | null | undefined): string {
  if (value === null || value === undefined) return 'unknown';
  if (value === 0) return '$0.00';
  if (value < 0.01) return `$${value.toFixed(4)}`;
  return `$${value.toFixed(2)}`;
}

export function formatTokens(count: number | undefined): string {
  if (!count) return '0';
  if (count < 1000) return String(count);
  return `${(count / 1000).toFixed(1)}k`;
}

export function formatArgs(args: Record<string, unknown>): string {
  const text = JSON.stringify(args);
  if (!text || text === '{}') return '—';
  return text.length <= 120 ? text : `${text.slice(0, 117)}...`;
}

export function statusTone(status: string): string {
  if (status === 'ok') return 'pill--ok';
  if (status === 'invalid' || status === 'denied') return 'pill--warn';
  if (status === 'error' || status === 'unknown') return 'pill--bad';
  return '';
}
