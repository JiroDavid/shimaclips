"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import DownloadPanel from "@/components/DownloadPanel";
import StreamerSearch from "@/components/StreamerSearch";
import { askQuestion, type AskMonth, type AskResult, type Clip } from "@/lib/api";
import { useDownload } from "@/lib/useDownload";

const EXAMPLES = [
  "Top 10 clips for each month of 2026 for jasontheween",
  "How many clips did jasontheween get this month?",
  "Find clips where he talks about boxing",
  "When did he do his island stream?",
];

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
      className="block overflow-hidden rounded border border-zinc-800 hover:border-zinc-600"
    >
      {clip.thumbnail_url && (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={clip.thumbnail_url} alt="" loading="lazy" className="aspect-video w-full object-cover" />
      )}
      <div className="space-y-0.5 p-2 text-xs">
        <p className="line-clamp-2">{clip.title || "Untitled clip"}</p>
        <p className="text-zinc-500">
          {clip.view_count.toLocaleString()} views - {clip.created_at.slice(0, 10)}
        </p>
      </div>
    </a>
  );
}

function Months({ months, onDownload, busy }: { months: AskMonth[]; onDownload: (c: Clip[]) => void; busy: boolean }) {
  const all = months.flatMap((m) => m.clips);
  return (
    <div className="space-y-4">
      <button
        onClick={() => onDownload(all)}
        disabled={busy || all.length === 0}
        className="rounded border border-zinc-700 px-3 py-2 text-sm hover:bg-zinc-800 disabled:opacity-50"
      >
        {busy ? "Downloading..." : `Download all ${all.length} clips`}
      </button>
      {months.map((m) => (
        <section key={m.month} className="space-y-2">
          <h3 className="text-sm font-semibold">
            {monthLabel(m.month)}
            {!m.exact && <span className="ml-2 text-xs font-normal text-amber-400">not fully loaded</span>}
          </h3>
          {m.clips.length === 0 ? (
            <p className="text-xs text-zinc-500">No clips loaded for this month.</p>
          ) : (
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
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
  if (turn.error) return <p className="text-sm text-red-400">{turn.error}</p>;
  if (!r) return <p className="text-sm text-zinc-400">Thinking...</p>;
  return (
    <div className="space-y-3">
      <p className="whitespace-pre-wrap text-sm">{r.answer}</p>
      {r.note && <p className="text-xs text-amber-400">{r.note}</p>}
      {!r.confident && r.kind === "answer" && r.sources.length > 0 && (
        <p className="text-xs text-amber-400">Low confidence: treat these clips as possible leads only.</p>
      )}
      {r.suggestions.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {r.suggestions.map((s) => (
            <button
              key={s.login}
              onClick={() => onPick(s.login, turn.question)}
              className="rounded-full border border-zinc-700 px-3 py-1 text-sm hover:bg-zinc-800"
            >
              {s.display_name}
              {s.is_live && <span className="ml-1 text-xs text-red-400">live</span>}
            </button>
          ))}
        </div>
      )}
      {r.months.length > 0 && <Months months={r.months} onDownload={onDownload} busy={downloading} />}
      {r.sources.length > 0 && (
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
          {r.sources.map((s) => (
            <ClipTile key={s.id} clip={{ ...s, thumbnail_url: s.thumbnail_url ?? "" }} />
          ))}
        </div>
      )}
      <p className="text-xs text-zinc-600">
        {r.tool ?? "no tool"} - {r.seconds}s - {r.usage.prompt_tokens + r.usage.output_tokens} tokens (local model)
        {r.streamer && (
          <>
            {" - "}
            <Link href={`/browse?streamer=${r.streamer.login}`} className="underline hover:text-zinc-300">
              open {r.streamer.display_name} in the calendar
            </Link>
          </>
        )}
      </p>
    </div>
  );
}

export default function AskChat() {
  const router = useRouter();
  const [turns, setTurns] = useState<Turn[]>([]);
  const [text, setText] = useState("");
  const [current, setCurrent] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const nextId = useRef(0);
  const bottom = useRef<HTMLDivElement>(null);
  const download = useDownload("ask");

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns]);

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

  const empty = turns.length === 0;

  const form = (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        void send(text);
      }}
      className="flex w-full gap-2"
    >
      <input
        value={text}
        onChange={(e) => setText(e.target.value)}
        maxLength={300}
        autoFocus
        aria-label="Ask a question about a streamer's clips"
        placeholder={current ? `Ask about ${current}'s clips or Twitch` : "Ask about a streamer's clips, for example top clips for jasontheween this month"}
        className={`flex-1 rounded-2xl border border-zinc-700 bg-zinc-900 px-5 text-base outline-none focus:border-zinc-400 ${empty ? "py-4" : "py-3"}`}
      />
      <button
        type="submit"
        disabled={busy || text.trim().length < 3}
        className="rounded-2xl bg-zinc-100 px-5 text-sm font-medium text-zinc-900 hover:bg-white disabled:opacity-40"
      >
        {busy ? "Thinking" : "Ask"}
      </button>
    </form>
  );

  const lookup = (
    <div className="w-full max-w-xs opacity-50 transition-opacity focus-within:opacity-100 hover:opacity-100">
      <p className="mb-1 text-xs text-zinc-500">Or browse a streamer&apos;s calendar</p>
      <StreamerSearch onSelect={(login) => router.push(`/browse?streamer=${encodeURIComponent(login)}`)} />
    </div>
  );

  if (empty) {
    return (
      <main className="mx-auto flex min-h-screen max-w-2xl flex-col items-center justify-center gap-6 px-6 py-10">
        <div className="space-y-2 text-center">
          <h1 className="text-4xl font-bold">Shimaclips</h1>
          <p className="text-zinc-400">Ask me anything about a streamer&apos;s Twitch clips.</p>
        </div>
        {form}
        <div className="flex flex-wrap justify-center gap-2">
          {EXAMPLES.map((ex) => (
            <button
              key={ex}
              onClick={() => void send(ex)}
              className="rounded-full border border-zinc-800 px-3 py-1 text-xs text-zinc-400 hover:border-zinc-600 hover:text-zinc-200"
            >
              {ex}
            </button>
          ))}
        </div>
        <div className="pt-6">{lookup}</div>
      </main>
    );
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-5xl flex-col px-6">
      <header className="flex flex-wrap items-center justify-between gap-3 py-4">
        <h1 className="text-lg font-bold">Shimaclips</h1>
        <div className="flex items-center gap-3 text-sm text-zinc-400">
          {current && (
            <span>
              Talking about <span className="text-zinc-200">{current}</span>{" "}
              <button onClick={() => setCurrent(null)} className="underline hover:text-zinc-200">
                clear
              </button>
            </span>
          )}
        </div>
      </header>
      <div className="flex-1 space-y-6 pb-6" aria-live="polite">
        {turns.map((t) => (
          <div key={t.id} className="space-y-3">
            <p className="ml-auto w-fit max-w-[85%] rounded-2xl bg-zinc-800 px-4 py-2 text-sm">{t.question}</p>
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
        {download.error && <p className="text-sm text-red-400">{download.error}</p>}
        <div ref={bottom} />
      </div>
      <div className="sticky bottom-0 space-y-3 bg-black/80 py-4 backdrop-blur">
        {form}
        <div className="flex justify-center">{lookup}</div>
      </div>
    </main>
  );
}
