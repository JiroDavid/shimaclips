"use client";

import { useRef, useState } from "react";
import { askQuestion, type AskResult } from "@/lib/api";

const EXAMPLES = [
  "What are the top 10 clips this month?",
  "How many clips does he have this month?",
  "Find clips where he talks about a car",
  "When did he do his island stream?",
];

export default function AskPanel({ login }: { login: string }) {
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<AskResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const latest = useRef(0);

  async function submit(q: string) {
    const text = q.trim();
    if (text.length < 3) return;
    const id = ++latest.current;
    setBusy(true);
    setError(null);
    try {
      const r = await askQuestion(login, text);
      if (id === latest.current) setResult(r);
    } catch (e) {
      if (id === latest.current) setError(e instanceof Error ? e.message : "Request failed");
    } finally {
      if (id === latest.current) setBusy(false);
    }
  }

  return (
    <section className="space-y-3 rounded border border-zinc-800 p-3">
      <h2 className="text-sm font-semibold">Ask about {login}&apos;s clips</h2>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void submit(question);
        }}
        className="flex gap-2"
      >
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          maxLength={300}
          placeholder="Ask a question about this streamer's clips"
          className="flex-1 rounded border border-zinc-700 bg-transparent px-3 py-2 text-sm"
        />
        <button
          type="submit"
          disabled={busy || question.trim().length < 3}
          className="rounded border border-zinc-700 px-3 py-2 text-sm hover:bg-zinc-800 disabled:opacity-50"
        >
          {busy ? "Thinking" : "Ask"}
        </button>
      </form>
      <div className="flex flex-wrap gap-2">
        {EXAMPLES.map((ex) => (
          <button
            key={ex}
            onClick={() => {
              setQuestion(ex);
              void submit(ex);
            }}
            className="rounded-full border border-zinc-700 px-2 py-1 text-xs text-zinc-300 hover:bg-zinc-800"
          >
            {ex}
          </button>
        ))}
      </div>
      {error && <p className="text-sm text-red-400">{error}</p>}
      {result && (
        <div className="space-y-2">
          <p className="whitespace-pre-wrap text-sm">{result.answer}</p>
          {!result.confident && (
            <p className="text-xs text-amber-400">Low confidence: treat these clips as possible leads only.</p>
          )}
          {result.sources.length > 0 && (
            <ol className="space-y-1">
              {result.sources.map((s, i) => (
                <li key={s.id} className="text-sm">
                  <span className="text-zinc-500">[{i + 1}] </span>
                  <a href={s.url} target="_blank" rel="noreferrer" className="underline hover:text-zinc-200">
                    {s.title || "Untitled clip"}
                  </a>
                  <span className="text-zinc-500">
                    {" "}
                    {s.created_at.slice(0, 10)} - {s.view_count.toLocaleString()} views
                    {s.score !== undefined && ` - match ${s.score.toFixed(2)}`}
                  </span>
                </li>
              ))}
            </ol>
          )}
          <p className="text-xs text-zinc-500">
            {result.tool ?? "no tool"} - {result.seconds}s - {result.usage.prompt_tokens + result.usage.output_tokens} tokens (local model)
          </p>
        </div>
      )}
    </section>
  );
}
