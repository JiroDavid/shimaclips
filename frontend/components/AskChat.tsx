"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import ClipCard from "@/components/ClipCard";
import ClipPreview, { PreviewContext } from "@/components/ClipPreview";
import DownloadPanel from "@/components/DownloadPanel";
import Logo from "@/components/Logo";
import Sidebar from "@/components/Sidebar";
import TranscriptionProgress from "@/components/TranscriptionProgress";
import {
  askQuestion,
  deleteConversation,
  getConversation,
  listConversations,
  type AskMonth,
  type AskResult,
  type Clip,
  type ConversationSummary,
} from "@/lib/api";
import { createPreviewController } from "@/lib/previewController";
import { emptySelection, pluralClips, toggleClip, type Selection } from "@/lib/selection";
import { useDownload } from "@/lib/useDownload";

const EXAMPLES = [
  "Top 10 clips from last month for arky",
  "How many clips did shroud get in 2025?",
  "Top 5 clips of each month of 2025 for stableronaldo",
  "Top 5 clips this month for marlon",
];

const LABEL = "text-xs uppercase tracking-[0.2em] text-zinc-500";
const FIELD = "border border-zinc-700 bg-zinc-900 outline-none focus:border-zinc-400";
const INK_BUTTON = "bg-zinc-100 text-zinc-900 hover:bg-white disabled:opacity-40";

type Turn = { id: number; question: string; result: AskResult | null; error: string | null };

function safeHref(url: string): string | undefined {
  try {
    const u = new URL(url);
    return u.protocol === "http:" || u.protocol === "https:" ? u.href : undefined;
  } catch {
    return undefined;
  }
}

function monthLabel(key: string): string {
  const [y, m] = key.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, 1)).toLocaleString("en", { month: "long", year: "numeric", timeZone: "UTC" });
}

type Picker = { selection: Selection; onToggle: (clip: Clip) => void };

function ClipGrid({ clips, picker }: { clips: Clip[]; picker: Picker }) {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
      {clips.map((c, i) => (
        <ClipCard key={c.id} clip={c} rank={i + 1} checked={picker.selection.has(c.id)} onToggle={() => picker.onToggle(c)} />
      ))}
    </div>
  );
}

function Months({ months, onDownload, busy, picker }: { months: AskMonth[]; onDownload: (c: Clip[]) => void; busy: boolean; picker: Picker }) {
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
            <ClipGrid clips={m.clips} picker={picker} />
          )}
        </section>
      ))}
    </div>
  );
}

function Avatar() {
  return <Logo className="h-10 w-10 shrink-0" />;
}

function Thinking() {
  return (
    <p className="flex items-center gap-2 text-base text-zinc-400" role="status">
      Thinking
      <span className="flex gap-1" aria-hidden>
        {[0, 150, 300].map((d) => (
          <span key={d} className="h-1.5 w-1.5 animate-pulse rounded-full bg-zinc-400" style={{ animationDelay: `${d}ms` }} />
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
  picker,
}: {
  turn: Turn;
  onPick: (login: string, question: string) => void;
  onDownload: (c: Clip[]) => void;
  downloading: boolean;
  picker: Picker;
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
            {r.transcription && (
              <TranscriptionProgress
                key={r.transcription.login}
                initial={r.transcription}
                onSearchAgain={() => onPick(r.transcription!.login, turn.question)}
              />
            )}
            {r.web_sources && r.web_sources.length > 0 && (
              <div className="space-y-1.5 rounded-xl border border-zinc-800 bg-zinc-900 px-4 py-3">
                <p className={LABEL}>Sources from the web</p>
                <ol className="space-y-1 text-sm">
                  {r.web_sources.map((w) => (
                    <li key={w.n} className="truncate">
                      <span className="text-zinc-500">[{w.n}] </span>
                      {safeHref(w.url) ? (
                        <a href={safeHref(w.url)} target="_blank" rel="noreferrer" className="underline hover:text-zinc-50">
                          {w.title || w.domain}
                        </a>
                      ) : (
                        <span>{w.title || w.domain}</span>
                      )}
                      <span className="text-zinc-500"> - {w.domain}</span>
                    </li>
                  ))}
                </ol>
              </div>
            )}
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
            {r.months.length > 0 && <Months months={r.months} onDownload={onDownload} busy={downloading} picker={picker} />}
            {r.sources.length > 0 && <ClipGrid clips={r.sources} picker={picker} />}
            {r.after && <p className="text-base leading-relaxed text-zinc-300">{r.after}</p>}
            <p className="border-t border-zinc-800 pt-3 text-xs text-zinc-500">
              {r.web ? "web search" : (r.tool ?? "no tool")} - {r.seconds}s - {r.usage.prompt_tokens + r.usage.output_tokens} tokens (local model)
              {r.web?.cached && " - cached answer"}
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
  const [turns, setTurns] = useState<Turn[]>([]);
  const [text, setText] = useState("");
  const [current, setCurrent] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const nextId = useRef(0);
  const thread = useRef(0);
  const activeRef = useRef<string | null>(null);
  const lastTurn = useRef<HTMLDivElement>(null);
  const download = useDownload("ask");
  const [preview] = useState(() => createPreviewController({}));
  const [selection, setSelection] = useState<Selection>(emptySelection());
  const picker: Picker = { selection, onToggle: (clip) => setSelection((sel) => toggleClip(sel, clip)) };
  useEffect(() => () => preview.close(), [preview]);
  const count = turns.length;

  const refreshList = useCallback(async () => {
    try {
      setConversations(await listConversations());
      setHistoryError(null);
    } catch {
      setHistoryError("History is unavailable right now.");
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    listConversations()
      .then((list) => {
        if (!cancelled) setConversations(list);
      })
      .catch(() => {
        if (!cancelled) setHistoryError("History is unavailable right now.");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (count > 0) lastTurn.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [count, activeId]);

  function newChat() {
    thread.current += 1;
    activeRef.current = null;
    preview.close();
    setActiveId(null);
    setTurns([]);
    setCurrent(null);
    setText("");
    setBusy(false);
    setSelection(emptySelection());
  }

  async function openConversation(id: string) {
    if (id === activeRef.current) return;
    const mine = ++thread.current;
    preview.close();
    setBusy(false);
    try {
      const c = await getConversation(id);
      if (mine !== thread.current) return;
      activeRef.current = c.id;
      setActiveId(c.id);
      setTurns(c.turns.map((t) => ({ id: nextId.current++, question: t.question, result: t.result, error: null })));
      setCurrent([...c.turns].reverse().find((t) => t.result.streamer)?.result.streamer?.login ?? null);
      setSelection(emptySelection());
      setHistoryError(null);
    } catch {
      if (mine === thread.current) setHistoryError("Could not open that chat.");
      void refreshList();
    }
  }

  async function removeConversation(id: string) {
    const title = conversations.find((c) => c.id === id)?.title ?? "this chat";
    if (!window.confirm(`Delete "${title}"? This cannot be undone.`)) return;
    try {
      await deleteConversation(id);
      if (activeRef.current === id) newChat();
    } catch {
      setHistoryError("Could not delete that chat.");
    }
    void refreshList();
  }

  async function send(question: string, login: string | null = current) {
    const q = question.trim();
    if (q.length < 3 || busy) return;
    const mine = thread.current;
    const id = nextId.current++;
    setBusy(true);
    setText("");
    setTurns((t) => [...t, { id, question: q, result: null, error: null }]);
    const patch = (p: Partial<Turn>) => setTurns((t) => t.map((x) => (x.id === id ? { ...x, ...p } : x)));
    try {
      const result = await askQuestion(q, login, activeRef.current);
      void refreshList();
      if (mine !== thread.current) return;
      if (result.conversation_id) {
        activeRef.current = result.conversation_id;
        setActiveId(result.conversation_id);
      }
      patch({ result });
      if (result.streamer) setCurrent(result.streamer.login);
    } catch (e) {
      if (mine === thread.current) patch({ error: e instanceof Error ? e.message : "Request failed" });
    } finally {
      if (mine === thread.current) setBusy(false);
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

  const content = empty ? (
    <main className="mx-auto flex min-h-screen w-full max-w-3xl flex-col items-center justify-center gap-8 px-6 py-10">
      <div className="space-y-3 text-center">
        <Logo className="mx-auto h-24 w-24" />
        <h1 className="text-5xl font-semibold tracking-tight">What clips are you after?</h1>
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
    </main>
  ) : (
    <main className="mx-auto flex min-h-screen w-full max-w-5xl flex-col px-8">
      <div className="flex h-14 items-center justify-end text-sm text-zinc-400">
        {current && (
          <span>
            Talking about <span className="font-medium text-zinc-50">{current}</span>{" "}
            <button onClick={() => setCurrent(null)} className="underline hover:text-zinc-50">
              clear
            </button>
          </span>
        )}
      </div>
      <div className="flex-1 space-y-12 py-6" aria-live="polite">
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
              picker={picker}
            />
          </div>
        ))}
        {download.job && <DownloadPanel state={download.job} />}
        {download.error && <p className="text-base text-red-400">{download.error}</p>}
        <div className="h-[55vh]" aria-hidden />
      </div>
      <div className="sticky bottom-0 bg-zinc-950 pb-8 pt-2">
        <div className="pointer-events-none absolute inset-x-0 -top-10 h-10 bg-gradient-to-t from-zinc-950 to-transparent" />
        {selection.size > 0 && (
          <div className="mb-3 flex items-center justify-between gap-3 rounded-xl border border-zinc-700 bg-zinc-900 px-4 py-2 text-sm">
            <span>{pluralClips(selection.size)}</span>
            <span className="flex gap-2">
              <button
                onClick={() => void download.start(Array.from(selection.values()))}
                disabled={download.downloading}
                className="rounded-full bg-zinc-100 px-4 py-1.5 font-medium text-zinc-900 hover:bg-white disabled:opacity-50"
              >
                {download.downloading ? "Downloading..." : "Download"}
              </button>
              <button onClick={() => setSelection(emptySelection())} className="rounded-full border border-zinc-700 px-4 py-1.5 hover:bg-zinc-800">
                Clear
              </button>
            </span>
          </div>
        )}
        {form}
      </div>
    </main>
  );

  return (
    <PreviewContext.Provider value={preview}>
      <div className="flex min-h-screen">
        <Sidebar
          open={sidebarOpen}
          onToggle={() => setSidebarOpen((v) => !v)}
          conversations={conversations}
          activeId={activeId}
          error={historyError}
          onNew={newChat}
          onOpen={(id) => void openConversation(id)}
          onDelete={(id) => void removeConversation(id)}
        />
        <div className="min-w-0 flex-1">{content}</div>
      </div>
      <ClipPreview controller={preview} />
    </PreviewContext.Provider>
  );
}
