"use client";

import { useMemo, useState } from "react";
import {
  heatLevel,
  isCellDisabled,
  monthDays,
  shiftMonth,
  shiftWeek,
  todayUtc,
  weekDays,
  type View,
} from "@/lib/calendar";
import { useCalendar } from "@/lib/useCalendar";

const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];
const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

const LEVEL_CLASS = [
  "bg-zinc-800 hover:bg-zinc-700",
  "bg-[#0e4429] hover:bg-[#12573a]",
  "bg-[#006d32] hover:bg-[#08833f]",
  "bg-[#26a641] hover:bg-[#32bd4f]",
  "bg-[#39d353] text-zinc-950 hover:bg-[#52e06a]",
  "bg-[#7ee787] text-zinc-950 hover:bg-[#98f0a0]",
] as const;

const DISABLED_CLASS = "cursor-not-allowed bg-zinc-700 opacity-50";
const FUTURE_CLASS = "cursor-not-allowed bg-zinc-900 opacity-40";
const APPROX_CLASS = "border border-dashed border-zinc-400/60";

type Cell = {
  key: string;
  start: string;
  end: string;
  label: string;
  aria: string;
  small?: string;
};

type Props = {
  login: string;
  tick: number;
  accountCreated: string;
  selectedKey: string | null;
  onSelect: (key: string | null) => void;
};

function navButton(disabled: boolean, label: string, onClick: () => void, text: string) {
  return (
    <button
      type="button"
      aria-label={label}
      disabled={disabled}
      onClick={onClick}
      className="rounded border border-zinc-700 px-3 py-1 text-sm hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-transparent"
    >
      {text}
    </button>
  );
}

export default function CalendarView({ login, tick, accountCreated, selectedKey, onSelect }: Props) {
  const today = todayUtc();
  const created = accountCreated.slice(0, 10);
  const nowYear = Number(today.slice(0, 4));
  const createdYear = Number(created.slice(0, 4));
  const nowMonth = today.slice(0, 7);
  const createdMonth = created.slice(0, 7);
  const firstWeek = weekDays(created)[0];
  const lastWeek = weekDays(today)[0];

  const [view, setView] = useState<View>("year");
  const [year, setYear] = useState(nowYear);
  const [month, setMonth] = useState(nowMonth);
  const [weekAnchor, setWeekAnchor] = useState(today);

  const monthYear = Number(month.slice(0, 4));
  const monthNum = Number(month.slice(5, 7));
  const weekStart = weekDays(weekAnchor)[0];

  const range = useMemo(() => {
    if (view === "year") return { granularity: "month" as const, start: `${year}-01-01`, end: `${year}-12-31` };
    if (view === "month") {
      const days = monthDays(monthYear, monthNum);
      return { granularity: "day" as const, start: days[0], end: days[days.length - 1] };
    }
    const days = weekDays(weekAnchor);
    return { granularity: "day" as const, start: days[0], end: days[6] };
  }, [view, year, monthYear, monthNum, weekAnchor]);

  const { buckets, loading, error } = useCalendar(login, range.granularity, range.start, range.end, tick);
  const byKey = useMemo(() => new Map(buckets.map((b) => [b.key, b])), [buckets]);

  let cells: Cell[] = [];
  let leading = 0;
  if (view === "year") {
    cells = MONTHS.map((name, i) => {
      const key = `${year}-${String(i + 1).padStart(2, "0")}`;
      const days = monthDays(year, i + 1);
      return { key, start: days[0], end: days[days.length - 1], label: name.slice(0, 3), aria: `${name} ${year}` };
    });
  } else if (view === "month") {
    const days = monthDays(monthYear, monthNum);
    leading = (new Date(Date.UTC(monthYear, monthNum - 1, 1)).getUTCDay() + 6) % 7;
    cells = days.map((d) => ({
      key: d,
      start: d,
      end: d,
      label: String(Number(d.slice(8))),
      aria: d,
    }));
  } else {
    cells = weekDays(weekAnchor).map((d, i) => ({
      key: d,
      start: d,
      end: d,
      label: `${WEEKDAYS[i]} ${Number(d.slice(8))}`,
      aria: d,
    }));
  }

  const state = cells.map((c) => {
    const b = byKey.get(c.key);
    const bucketState = b?.state;
    const count = b?.count ?? 0;
    const dateDisabled = c.start > today || c.end < created;
    return {
      cell: c,
      bucketState,
      count,
      dateDisabled,
      disabled: isCellDisabled(c.start, c.end, created, today, bucketState),
    };
  });

  const active = state.filter((s) => !s.disabled);
  const max = active.reduce((m, s) => Math.max(m, s.count), 0);
  const allExact = state.every((s) => s.bucketState === "exact" || s.dateDisabled);
  const empty = allExact && active.length > 0 && max === 0;

  let title = "";
  let canPrev = false;
  let canNext = false;
  let prev = () => {};
  let next = () => {};
  if (view === "year") {
    title = String(year);
    canPrev = year > createdYear;
    canNext = year < nowYear;
    prev = () => setYear((y) => Math.max(createdYear, y - 1));
    next = () => setYear((y) => Math.min(nowYear, y + 1));
  } else if (view === "month") {
    title = `${MONTHS[monthNum - 1]} ${monthYear}`;
    canPrev = month > createdMonth;
    canNext = month < nowMonth;
    prev = () => setMonth((m) => (m > createdMonth ? shiftMonth(m, -1) : m));
    next = () => setMonth((m) => (m < nowMonth ? shiftMonth(m, 1) : m));
  } else {
    const days = weekDays(weekAnchor);
    title = `${days[0]} to ${days[6]}`;
    canPrev = weekStart > firstWeek;
    canNext = weekStart < lastWeek;
    prev = () => setWeekAnchor((a) => (weekDays(a)[0] > firstWeek ? shiftWeek(a, -1) : a));
    next = () => setWeekAnchor((a) => (weekDays(a)[0] < lastWeek ? shiftWeek(a, 1) : a));
  }

  function describe(s: (typeof state)[number]): string {
    if (s.dateDisabled) return `${s.cell.aria}, outside the account lifetime`;
    if (s.bucketState === "approximate") {
      return `${s.cell.aria}, about ${s.count.toLocaleString()} clips so far - approximate, still loading exact counts`;
    }
    if (s.bucketState !== "exact") return `${s.cell.aria}, not loaded yet`;
    return `${s.cell.aria}, ${s.count} ${s.count === 1 ? "clip" : "clips"}`;
  }

  function renderCell(s: (typeof state)[number], big: boolean) {
    const selected = selectedKey === s.cell.key;
    const level = heatLevel(s.count, max);
    const tone = s.disabled ? (s.dateDisabled ? FUTURE_CLASS : DISABLED_CLASS) : LEVEL_CLASS[level];
    const approximate = s.bucketState === "approximate" && !s.disabled;
    const countText = s.dateDisabled
      ? "-"
      : approximate
        ? `${s.count.toLocaleString()}+`
        : s.bucketState === "exact"
          ? String(s.count)
          : big
            ? "loading"
            : "";
    return (
      <button
        key={s.cell.key}
        type="button"
        disabled={s.disabled}
        aria-label={describe(s)}
        aria-pressed={selected}
        title={approximate ? describe(s) : !s.disabled && s.count === 0 ? "no clips" : undefined}
        onClick={() => onSelect(selected ? null : s.cell.key)}
        className={`flex flex-col items-center justify-center rounded-lg p-2 ${big ? "min-h-16" : "min-h-12"} ${tone} ${approximate ? APPROX_CLASS : ""} ${
          selected ? "ring-2 ring-white ring-offset-2 ring-offset-zinc-950" : ""
        }`}
      >
        <span className={big ? "text-sm font-semibold" : "text-sm"}>{s.cell.label}</span>
        <span className="text-xs opacity-80">{countText}</span>
      </button>
    );
  }

  return (
    <section className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="inline-flex overflow-hidden rounded border border-zinc-700" role="group" aria-label="Calendar view">
          {(["year", "month", "week"] as const).map((v) => (
            <button
              key={v}
              type="button"
              aria-pressed={view === v}
              onClick={() => setView(v)}
              className={`px-3 py-1 text-sm capitalize ${view === v ? "bg-purple-600 text-white" : "hover:bg-zinc-800"}`}
            >
              {v}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-3">
          {navButton(!canPrev, "Previous", prev, "<")}
          <span className="min-w-32 text-center font-semibold">{title}</span>
          {navButton(!canNext, "Next", next, ">")}
        </div>
      </div>

      {error && <p className="text-sm text-red-400">{error}</p>}

      <div className={loading ? "opacity-90" : undefined} aria-busy={loading}>
        {view === "year" && <div className="grid grid-cols-3 gap-2 sm:grid-cols-6">{state.map((s) => renderCell(s, true))}</div>}
        {view === "month" && (
          <div className="grid grid-cols-7 gap-1.5">
            {WEEKDAYS.map((w) => (
              <span key={w} className="text-center text-xs text-zinc-400">
                {w}
              </span>
            ))}
            {Array.from({ length: leading }, (_, i) => (
              <span key={`blank-${i}`} />
            ))}
            {state.map((s) => renderCell(s, false))}
          </div>
        )}
        {view === "week" && <div className="grid grid-cols-7 gap-1.5">{state.map((s) => renderCell(s, false))}</div>}
      </div>

      {empty && <p className="text-sm text-zinc-400">No clips in this period</p>}

      <div className="flex items-center gap-2 text-xs text-zinc-400">
        <span>less</span>
        {[0, 1, 2, 3, 4, 5].map((l) => (
          <span key={l} className={`inline-block h-3 w-3 rounded-sm ${LEVEL_CLASS[l].split(" ")[0]}`} />
        ))}
        <span>more</span>
        <span className={`ml-2 inline-block h-3 w-3 rounded-sm bg-zinc-800 ${APPROX_CLASS}`} />
        <span>approximate</span>
      </div>
    </section>
  );
}
