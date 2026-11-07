export type View = "year" | "month" | "week";

const DAY_MS = 86400000;

function pad(n: number): string {
  return String(n).padStart(2, "0");
}

function fmt(d: Date): string {
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}`;
}

function parse(day: string): Date {
  const [y, m, d] = day.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d));
}

export function monthDays(year: number, month: number): string[] {
  const count = new Date(Date.UTC(year, month, 0)).getUTCDate();
  return Array.from({ length: count }, (_, i) => `${year}-${pad(month)}-${pad(i + 1)}`);
}

export function weekDays(anchor: string): string[] {
  const d = parse(anchor);
  const offset = (d.getUTCDay() + 6) % 7;
  const monday = d.getTime() - offset * DAY_MS;
  return Array.from({ length: 7 }, (_, i) => fmt(new Date(monday + i * DAY_MS)));
}

export function shiftMonth(key: string, delta: number): string {
  const [y, m] = key.split("-").map(Number);
  const d = new Date(Date.UTC(y, m - 1 + delta, 1));
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}`;
}

export function shiftWeek(anchor: string, delta: number): string {
  return fmt(new Date(parse(anchor).getTime() + delta * 7 * DAY_MS));
}

export function heatLevel(count: number, max: number): 0 | 1 | 2 | 3 | 4 | 5 {
  if (count <= 0 || max <= 0) return 0;
  return Math.min(5, Math.max(1, Math.ceil((count / max) * 5))) as 1 | 2 | 3 | 4 | 5;
}

export function rangeOfKey(key: string): { start: string; end: string } {
  const parts = key.split("-").map(Number);
  if (parts.length === 1) return { start: `${parts[0]}-01-01`, end: `${parts[0]}-12-31` };
  if (parts.length === 2) {
    const days = monthDays(parts[0], parts[1]);
    return { start: days[0], end: days[days.length - 1] };
  }
  return { start: key, end: key };
}

export function todayUtc(now: Date = new Date()): string {
  return fmt(now);
}

export function isCellDisabled(
  cellStart: string,
  cellEnd: string,
  accountCreated: string,
  today: string,
  ready: boolean,
): boolean {
  return !ready || cellStart > today || cellEnd < accountCreated;
}

const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

export function labelOfKey(key: string): string {
  const parts = key.split("-").map(Number);
  if (parts.length === 1) return String(parts[0]);
  if (parts.length === 2) return `${MONTH_NAMES[parts[1] - 1]} ${parts[0]}`;
  return `${MONTH_NAMES[parts[1] - 1]} ${parts[2]}, ${parts[0]}`;
}
