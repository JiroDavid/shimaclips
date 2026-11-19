"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import DownloadPanel from "@/components/DownloadPanel";
import StreamerSearch from "@/components/StreamerSearch";
import { askQuestion, type AskMonth, type AskResult, type Clip } from "@/lib/api";
import { useDownload } from "@/lib/useDownload";

const EXAMPLES = [
  "Top 10 clips from last month for arky",
  "How many clips did shroud get in 2025?",
  "Top 5 clips of each month of 2025 for stableronaldo",
  "Top 5 clips this month for yugi",
];

const LABEL = "text-xs uppercase tracking-[0.2em] text-zinc-500";
const FIELD = "border border-zinc-800 bg-zinc-900 outline-none placeholder:text-zinc-500 focus:border-zinc-600";
const INK_BUTTON = "bg-accent-strong text-white hover:bg-accent disabled:opacity-40";

type Turn = { id: number; question: string; result: AskResult | null; error: string | null };

function monthLabel(key: string): string {
  const [y, m] = key.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, 1)).toLocaleString("en", { month: "long", year: "numeric", timeZone: "UTC" });
}

function ClipTile({ clip }: { clip: Pick<Clip, "url" | "title" | "thumbnail_url" | "view_count" | "created_at"> }) {
  return (
    <a
      href={clip.url}
      target="_blank"
      rel="noreferrer"
      className="block overflow-hidden rounded-xl border border-zinc-800 bg-zinc-900 transition-colors hover:border-zinc-600"
    >
      {clip.thumbnail_url && (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={clip.thumbnail_url} alt="" loading="lazy" className="aspect-video w-full object-cover" />
      )}
      <div className="space-y-1 p-3">
        <p className="line-clamp-2 text-sm leading-snug">{clip.title || "Untitled clip"}</p>
        <p className="text-xs text-zinc-500">
          {clip.view_count.toLocaleString()} views - {clip.created_at.slice(0, 10)}
        </p>
      </div>
    </a>
  );
}

function Months({ months, onDownload, busy }: { months: AskMonth[]; onDownload: (c: Clip[]) => void; busy: boolean }) {
  const all = months.flatMap((m) => m.clips);
  return (
    <div className="space-y-6">
      <button
        onClick={() => onDownload(all)}
        disabled={busy || all.length === 0}
        className="rounded-full border border-zinc-700 px-4 py-2 text-sm hover:bg-zinc-900 disabled:opacity-50"
      >
        {busy ? "Downloading..." : `Download all ${all.length} clips`}
      </button>
      {months.map((m) => (
        <section key={m.month} className="space-y-3">
          <h3 className="flex items-baseline gap-3">
            <span className="text-base font-semibold">{monthLabel(m.month)}</span>
            {!m.exact && <span className="text-xs text-amber-400">not fully loaded</span>}
          </h3>
          {m.clips.length === 0 ? (
            <p className="text-sm text-zinc-500">No clips loaded for this month.</p>
          ) : (
            <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-5">
              {m.clips.map((c) => (
                <ClipTile key={c.id} clip={c} />
              ))}
            </div>
          )}
        </section>
      ))}
    </div>
  );
}

function Asterisk({ className }: { className: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round">
      {[0, 45, 90, 135].map((deg) => (
        <line key={deg} x1="12" y1="2.5" x2="12" y2="21.5" transform={`rotate(${deg} 12 12)`} />
      ))}
    </svg>
  );
}

function Avatar() {
  return <Asterisk className="mt-1 h-7 w-7 shrink-0 text-accent" />;
}

function Thinking() {
  return (
    <p className="flex items-center gap-2 text-base text-zinc-400" role="status">
      Thinking
      <span className="flex gap-1" aria-hidden>
        {[0, 150, 300].map((d) => (
          <span key={d} className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent" style={{ animationDelay: `${d}ms` }} />
        ))}
      </span>
    </p>
  );
}

function Answer({
  turn,
  onPick,
  onDownload,
  downloading,
}: {
  turn: Turn;
  onPick: (login: string, question: string) => void;
  onDownload: (c: Clip[]) => void;
  downloading: boolean;
}) {
  const r = turn.result;
  return (
    <div className="flex gap-4">
      <Avatar />
      <div className="min-w-0 flex-1 space-y-4 pt-1">
        <p className={LABEL}>Shimaclips</p>
        {turn.error && <p className="text-base text-red-400">{turn.error}</p>}
        {!turn.error && !r && <Thinking />}
        {r && (
          <>
            <p className="whitespace-pre-wrap text-base leading-relaxed">{r.answer}</p>
            {r.note && <p className="text-sm text-amber-400">{r.note}</p>}
            {!r.confident && r.kind === "answer" && r.sources.length > 0 && (
              <p className="text-sm text-amber-400">Low confidence: treat these clips as possible leads only.</p>
            )}
            {r.suggestions.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {r.suggestions.map((s) => (
                  <button
                    key={s.login}
                    onClick={() => onPick(s.login, turn.question)}
                    className="rounded-full border border-zinc-700 px-4 py-1.5 text-sm hover:bg-zinc-900"
                  >
                    {s.display_name}
                    {s.is_live && <span className="ml-1 text-xs text-red-400">live</span>}
                  </button>
                ))}
              </div>
            )}
            {r.months.length > 0 && <Months months={r.months} onDownload={onDownload} busy={downloading} />}
            {r.sources.length > 0 && (
              <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-5">
                {r.sources.map((s) => (
                  <ClipTile key={s.id} clip={{ ...s, thumbnail_url: s.thumbnail_url ?? "" }} />
                ))}
              </div>
            )}
            {r.after && <p className="text-base leading-relaxed text-zinc-300">{r.after}</p>}
            <p className="border-t border-zinc-800 pt-3 text-xs text-zinc-500">
              {r.tool ?? "no tool"} - {r.seconds}s - {r.usage.prompt_tokens + r.usage.output_tokens} tokens (local model)
              {r.streamer && (
                <>
                  {" - "}
                  <Link href={`/browse?streamer=${r.streamer.login}`} className="underline hover:text-zinc-50">
                    open {r.streamer.display_name} in the calendar
                  </Link>
                </>
              )}
            </p>
          </>
        )}
      </div>
    </div>
  );
}

export default function AskChat() {
  const router = useRouter();
  const [turns, setTurns] = useState<Turn[]>([]);
  const [text, setText] = useState("");
  const [current, setCurrent] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [lookupOpen, setLookupOpen] = useState(false);
  const nextId = useRef(0);
  const lastTurn = useRef<HTMLDivElement>(null);
  const download = useDownload("ask");
  const count = turns.length;

  useEffect(() => {
    if (count > 0) lastTurn.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [count]);

  async function send(question: string, login: string | null = current) {
    const q = question.trim();
    if (q.length < 3 || busy) return;
    const id = nextId.current++;
    setBusy(true);
    setText("");
    setTurns((t) => [...t, { id, question: q, result: null, error: null }]);
    const patch = (p: Partial<Turn>) => setTurns((t) => t.map((x) => (x.id === id ? { ...x, ...p } : x)));
    try {
      const result = await askQuestion(q, login);
      patch({ result });
      if (result.streamer) setCurrent(result.streamer.login);
    } catch (e) {
      patch({ error: e instanceof Error ? e.message : "Request failed" });
    } finally {
      setBusy(false);
    }
  }

  const empty = count === 0;

  const form = (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        void send(text);
      }}
      className="flex w-full gap-3"
    >
      <input
        value={text}
        onChange={(e) => setText(e.target.value)}
        maxLength={300}
        autoFocus
        aria-label="Ask a question about a streamer's clips"
        placeholder={current ? `Ask about ${current}'s clips or Twitch` : "Ask about any streamer's clips"}
        className={`flex-1 rounded-2xl px-6 ${FIELD} ${empty ? "py-5 text-lg" : "py-4 text-base"}`}
      />
      <button
        type="submit"
        disabled={busy || text.trim().length < 3}
        className={`rounded-2xl px-7 text-base font-medium ${INK_BUTTON}`}
      >
        {busy ? "Thinking" : "Ask"}
      </button>
    </form>
  );

  const renderLookup = (align: "center" | "right") => (
    <div className="relative flex flex-col items-center">
      <button
        onClick={() => setLookupOpen((v) => !v)}
        aria-expanded={lookupOpen}
        className="text-sm text-zinc-400 underline decoration-zinc-700 underline-offset-4 hover:text-zinc-50"
      >
        Browse a streamer&apos;s calendar
      </button>
      {lookupOpen && (
        <div className={`absolute top-full z-10 mt-2 w-80 ${align === "center" ? "left-1/2 -translate-x-1/2" : "right-0"}`}>
          <StreamerSearch onSelect={(login) => router.push(`/browse?streamer=${encodeURIComponent(login)}`)} />
        </div>
      )}
    </div>
  );

  if (empty) {
    return (
      <div className="theme-warm min-h-screen">
      <main className="mx-auto flex min-h-screen w-full max-w-3xl flex-col items-center justify-center gap-8 px-6 py-10">
        <div className="space-y-3 text-center">
          <Asterisk className="mx-auto h-10 w-10 text-accent" />
          <h1 className="font-serif text-5xl tracking-tight">What clips are you after?</h1>
          <p className="text-lg text-zinc-400">Ask about any Twitch streamer and their clips.</p>
        </div>
        {form}
        <div className="flex flex-wrap justify-center gap-2">
          {EXAMPLES.map((ex) => (
            <button
              key={ex}
              onClick={() => void send(ex)}
              className="rounded-full border border-zinc-800 px-4 py-2 text-sm text-zinc-300 hover:border-zinc-600 hover:bg-zinc-900"
            >
              {ex}
            </button>
          ))}
        </div>
        <div className="pt-4">{renderLookup("center")}</div>
      </main>
      </div>
    );
  }

  return (
    <div className="theme-warm min-h-screen">
    <main className="mx-auto flex min-h-screen w-full max-w-6xl flex-col px-8">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-zinc-800 py-5">
        <h1 className="text-sm font-semibold uppercase tracking-[0.3em] text-accent">Shimaclips</h1>
        <div className="flex flex-wrap items-center gap-5 text-sm text-zinc-400">
          {current && (
            <span>
              Talking about <span className="font-medium text-zinc-50">{current}</span>{" "}
              <button onClick={() => setCurrent(null)} className="underline hover:text-zinc-50">
                clear
              </button>
            </span>
          )}
          {renderLookup("right")}
        </div>
      </header>
      <div className="flex-1 space-y-12 py-10" aria-live="polite">
        {turns.map((t, i) => (
          <div key={t.id} ref={i === count - 1 ? lastTurn : undefined} className="scroll-mt-6 space-y-6">
            <p className="ml-auto w-fit max-w-[80%] rounded-2xl bg-zinc-900 px-5 py-3 text-base">{t.question}</p>
            <Answer
              turn={t}
              onPick={(login, q) => {
                setCurrent(login);
                void send(q, login);
              }}
              onDownload={(clips) => void download.start(clips)}
              downloading={download.downloading}
            />
          </div>
        ))}
        {download.job && <DownloadPanel state={download.job} />}
        {download.error && <p className="text-base text-red-400">{download.error}</p>}
        <div className="h-[55vh]" aria-hidden />
      </div>
      <div className="sticky bottom-0 bg-zinc-950 pb-8 pt-2">
        <div className="pointer-events-none absolute inset-x-0 -top-10 h-10 bg-gradient-to-t from-zinc-950 to-transparent" />
        {form}
      </div>
    </main>
    </div>
  );
}
