"use client";

import { useRef, useState } from "react";
import ClipCard from "@/components/ClipCard";
import DownloadPanel from "@/components/DownloadPanel";
import { fileUrl, searchClips, startDownload, watchJob, type Clip, type JobState } from "@/lib/api";

export default function Home() {
  const [streamer, setStreamer] = useState("");
  const [mode, setMode] = useState<"month" | "range">("month");
  const [month, setMonth] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [count, setCount] = useState(10);

  const [clips, setClips] = useState<Clip[] | null>(null);
  const [total, setTotal] = useState(0);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [job, setJob] = useState<JobState | null>(null);
  const stopWatching = useRef<(() => void) | null>(null);

  async function onSearch(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setJob(null);
    setSearching(true);
    try {
      const body = { streamer, count, ...(mode === "month" ? { month } : { start, end }) };
      const res = await searchClips(body);
      setClips(res.clips);
      setTotal(res.total_in_window);
      setSelected(new Set(res.clips.map((c) => c.id)));
    } catch (err) {
      setClips(null);
      setError(err instanceof Error ? err.message : "Search failed");
    } finally {
      setSearching(false);
    }
  }

  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function onDownload() {
    if (!clips) return;
    setError(null);
    stopWatching.current?.();
    const chosen = clips.filter((c) => selected.has(c.id));
    try {
      const jobId = await startDownload(chosen);
      setJob({ status: "running", error: null, items: [] });
      stopWatching.current = watchJob(jobId, (state) => {
        setJob(state);
        if (state.status === "done") {
          const a = document.createElement("a");
          a.href = fileUrl(jobId);
          a.click();
        }
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Download failed");
    }
  }

  const running = job?.status === "running";

  return (
    <main className="mx-auto max-w-6xl space-y-6 p-6">
      <h1 className="text-2xl font-bold">Shimaclips</h1>

      <form onSubmit={onSearch} className="flex flex-wrap items-end gap-4 rounded-lg border border-zinc-800 bg-zinc-900 p-4">
        <label className="space-y-1 text-sm">
          <span className="block text-zinc-400">Streamer</span>
          <input
            required
            value={streamer}
            onChange={(e) => setStreamer(e.target.value)}
            placeholder="jasontheween"
            className="rounded bg-zinc-800 px-3 py-2"
          />
        </label>

        <div className="space-y-1 text-sm">
          <span className="block text-zinc-400">Dates (UTC)</span>
          <div className="flex items-center gap-2">
            <select value={mode} onChange={(e) => setMode(e.target.value as "month" | "range")} className="rounded bg-zinc-800 px-2 py-2">
              <option value="month">Month</option>
              <option value="range">Date range</option>
            </select>
            {mode === "month" ? (
              <input type="month" required value={month} onChange={(e) => setMonth(e.target.value)} className="rounded bg-zinc-800 px-3 py-2" />
            ) : (
              <>
                <input type="date" required value={start} onChange={(e) => setStart(e.target.value)} className="rounded bg-zinc-800 px-3 py-2" />
                <span className="text-zinc-500">to</span>
                <input type="date" required value={end} onChange={(e) => setEnd(e.target.value)} className="rounded bg-zinc-800 px-3 py-2" />
              </>
            )}
          </div>
        </div>

        <label className="space-y-1 text-sm">
          <span className="block text-zinc-400">Top</span>
          <input
            type="number"
            min={1}
            max={200}
            value={count}
            onChange={(e) => setCount(Number(e.target.value))}
            className="w-20 rounded bg-zinc-800 px-3 py-2"
          />
        </label>

        <button disabled={searching} className="rounded bg-purple-600 px-4 py-2 font-medium hover:bg-purple-500 disabled:opacity-50">
          {searching ? "Searching..." : "Search"}
        </button>
      </form>

      {error && <p className="rounded border border-red-900 bg-red-950 p-3 text-sm text-red-300">{error}</p>}

      {clips && clips.length === 0 && (
        <p className="text-zinc-400">No clips found for that streamer in this window.</p>
      )}

      {clips && clips.length > 0 && (
        <>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm text-zinc-400">
              Showing top {clips.length} of {total} clips - {selected.size} selected
            </p>
            <div className="flex gap-3">
              <button
                onClick={() => setSelected(selected.size === clips.length ? new Set() : new Set(clips.map((c) => c.id)))}
                className="rounded border border-zinc-700 px-3 py-2 text-sm hover:bg-zinc-800"
              >
                {selected.size === clips.length ? "Select none" : "Select all"}
              </button>
              <button
                onClick={onDownload}
                disabled={selected.size === 0 || running}
                className="rounded bg-purple-600 px-4 py-2 text-sm font-medium hover:bg-purple-500 disabled:opacity-50"
              >
                Download {selected.size}
              </button>
            </div>
          </div>

          {job && <DownloadPanel state={job} />}

          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {clips.map((c, i) => (
              <ClipCard key={c.id} clip={c} rank={i + 1} checked={selected.has(c.id)} onToggle={() => toggle(c.id)} />
            ))}
          </div>
        </>
      )}
    </main>
  );
}
