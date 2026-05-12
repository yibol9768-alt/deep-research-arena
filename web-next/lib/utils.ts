import { type ClassValue, clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function fmtNum(n: number | null | undefined, opts?: { decimals?: number; suffix?: string }) {
  if (n == null || isNaN(n as number)) return '—';
  const d = opts?.decimals ?? 0;
  const fixed = d > 0 ? n.toFixed(d) : Math.round(n).toString();
  const [whole, frac] = fixed.split('.');
  const withCommas = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  return (frac ? withCommas + '.' + frac : withCommas) + (opts?.suffix ?? '');
}

export function fmtCount(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M';
  if (n >= 1_000) return Math.round(n / 1_000) + 'k';
  return n.toString();
}

export function fmtPct(n: number | null | undefined, decimals = 0): string {
  if (n == null) return '—';
  return (n * 100).toFixed(decimals) + '%';
}
