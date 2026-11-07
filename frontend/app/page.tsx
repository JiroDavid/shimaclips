"use client";

import { useState } from "react";
import CalendarView from "@/components/CalendarView";
import LoadingBanner from "@/components/LoadingBanner";
import StreamerEntry from "@/components/StreamerEntry";
import { useStreamer } from "@/lib/useStreamer";

export default function Home() {
  const { streamer, state, phase, error, tick, startedAt, open, refresh } = useStreamer();
  const [lastLogin, setLastLogin] = useState("");
  const [selection, setSelection] = useState<{ login: string; key: string } | null>(null);
  const selectedKey = streamer && selection?.login === streamer.login ? selection.key : null;

  const busy = phase === "opening" || phase === "loading";

  function submit(login: string) {
    setLastLogin(login);
    open(login);
  }

  function retry() {
    if (streamer) refresh(false);
    else open(lastLogin);
  }

  return (
    <main className="mx-auto max-w-6xl space-y-6 p-6">
      <h1 className="text-2xl font-bold">Shimaclips</h1>

      <StreamerEntry onSubmit={submit} />

      {(busy || phase === "error") && (
        <LoadingBanner state={state} startedAt={startedAt} error={phase === "error" ? error : null} onRetry={retry} />
      )}

      {streamer && (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-lg font-semibold">
            {streamer.display_name}{" "}
            <span className="text-sm font-normal text-zinc-400">
              account created {streamer.account_created.slice(0, 10)}
            </span>
          </p>
          <div className="flex gap-3">
            <button
              onClick={() => refresh(false)}
              disabled={busy}
              className="rounded border border-zinc-700 px-3 py-2 text-sm hover:bg-zinc-800 disabled:opacity-50"
            >
              Refresh
            </button>
            <button
              onClick={() => refresh(true)}
              disabled={busy}
              className="rounded border border-zinc-700 px-3 py-2 text-sm hover:bg-zinc-800 disabled:opacity-50"
            >
              Full refresh
            </button>
          </div>
        </div>
      )}

      {streamer && (
        <>
          <CalendarView
            key={streamer.login}
            login={streamer.login}
            tick={tick}
            accountCreated={streamer.account_created}
            selectedKey={selectedKey}
            onSelect={(key) => setSelection(key ? { login: streamer.login, key } : null)}
          />
          {selectedKey && (
            <p className="text-sm text-zinc-400">
              Selected: {selectedKey}{" "}
              <button onClick={() => setSelection(null)} className="underline hover:text-zinc-200">
                Clear
              </button>
            </p>
          )}
        </>
      )}
    </main>
  );
}
