"use client";

import { useEffect, useState } from "react";
import { getTranscription, startTranscription, type Transcription } from "@/lib/api";

const ACTIVE = ["queued", "finding", "transcribing", "indexing"];
const POLL_MS = 2000;

function describe(s: Transcription): string {
  switch (s.state) {
    case "queued":
      return "Waiting to start...";
    case "finding":
      return "Finding their top clips from the last year...";
    case "transcribing":
      return `${s.processed.toLocaleString()} of ${s.total.toLocaleString()} clips`;
    case "indexing":
      return "Updating the search index...";
    case "done":
      return `Done: ${s.transcribed.toLocaleString()} clips are searchable now.`;
    case "error":
      return s.error ?? "Something went wrong.";
    default:
      return "Not transcribed yet.";
  }
}

export default function TranscriptionProgress({
  initial,
  onSearchAgain,
}: {
  initial: Transcription;
  onSearchAgain: () => void;
}) {
  const [status, setStatus] = useState(initial);
  const [lost, setLost] = useState(false);
  const [starting, setStarting] = useState(false);
  const active = ACTIVE.includes(status.state);

  useEffect(() => {
    if (!active) return;
    let cancelled = false;
    const timer = setTimeout(async () => {
      try {
        const next = await getTranscription(status.login);
        if (cancelled) return;
        setLost(false);
        setStatus(next);
      } catch {
        if (!cancelled) setLost(true);
      }
    }, POLL_MS);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [status, active, lost]);

  async function start() {
    setStarting(true);
    try {
      setStatus(await startTranscription(status.login));
      setLost(false);
    } catch {
      setLost(true);
    } finally {
      setStarting(false);
    }
  }

  const pct = status.state === "transcribing" && status.total > 0 ? Math.min(100, Math.round((status.processed / status.total) * 100)) : status.state === "done" ? 100 : 0;
  const indeterminate = status.state === "queued" || status.state === "finding";

  return (
    <div className="space-y-3 rounded-xl border border-zinc-800 bg-zinc-900 p-4">
      <div className="flex items-baseline justify-between gap-3">
        <p className="text-xs uppercase tracking-[0.2em] text-zinc-500">Transcribing {status.display_name}&apos;s clips</p>
        {status.state === "transcribing" && <span className="text-sm text-zinc-400">{pct}%</span>}
      </div>
      <div
        role="progressbar"
        aria-label="Transcription progress"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={indeterminate ? undefined : pct}
        className="h-2 overflow-hidden rounded-full bg-zinc-800"
      >
        <div
          className={`h-full rounded-full bg-zinc-100 transition-all duration-500 ${indeterminate ? "w-1/3 animate-pulse" : ""}`}
          style={indeterminate ? undefined : { width: `${pct}%` }}
        />
      </div>
      <p className={`text-sm ${status.state === "error" ? "text-red-400" : "text-zinc-300"}`}>{describe(status)}</p>
      {lost && active && <p className="text-xs text-amber-400">Lost contact with the server, retrying...</p>}
      <div className="flex flex-wrap gap-2">
        {(status.state === "transcribing" || status.state === "indexing" || status.state === "done") && status.transcribed > 0 && (
          <button onClick={onSearchAgain} className="rounded-full border border-zinc-700 px-4 py-1.5 text-sm hover:bg-zinc-800">
            Search again
          </button>
        )}
        {(status.state === "idle" || status.state === "error") && (
          <button
            onClick={() => void start()}
            disabled={starting}
            className="rounded-full bg-zinc-100 px-4 py-1.5 text-sm font-medium text-zinc-900 hover:bg-white disabled:opacity-50"
          >
            {starting ? "Starting..." : status.state === "error" ? "Try again" : "Start transcribing"}
          </button>
        )}
      </div>
    </div>
  );
}
