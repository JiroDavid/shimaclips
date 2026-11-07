"use client";

import { useState } from "react";
import CalendarView from "@/components/CalendarView";
import DownloadPanel from "@/components/DownloadPanel";
import LoadingBanner from "@/components/LoadingBanner";
import ReelSection from "@/components/ReelSection";
import SelectionPanel from "@/components/SelectionPanel";
import StreamerEntry from "@/components/StreamerEntry";
import { labelOfKey, rangeOfKey, todayUtc } from "@/lib/calendar";
import { emptySelection, removeClip, toggleClip, type Selection } from "@/lib/selection";
import type { Clip } from "@/lib/api";
import { useDownload } from "@/lib/useDownload";
import { useStreamer } from "@/lib/useStreamer";

export default function Home() {
  const { streamer, state, phase, error, tick, startedAt, open, refresh } = useStreamer();
  const [lastLogin, setLastLogin] = useState("");
  const [selection, setSelection] = useState<{ login: string; key: string } | null>(null);
  const selectedKey = streamer && selection?.login === streamer.login ? selection.key : null;

  const [picked, setPicked] = useState<{ login: string; sel: Selection } | null>(null);
  const clipSelection = streamer && picked?.login === streamer.login ? picked.sel : emptySelection();

  const download = useDownload(streamer?.login ?? null);

  const busy = phase === "opening" || phase === "loading";

  function reelList() {
    const today = todayUtc();
    return [
      { key: "month", title: "Top clips this month", range: rangeOfKey(today.slice(0, 7)) },
      { key: "year", title: "Top clips this year", range: rangeOfKey(today.slice(0, 4)) },
      { key: "all", title: "Most viewed of all time", range: {} },
    ];
  }

  function toggle(clip: Clip) {
    if (!streamer) return;
    setPicked({ login: streamer.login, sel: toggleClip(clipSelection, clip) });
  }

  function remove(id: string) {
    if (!streamer) return;
    setPicked({ login: streamer.login, sel: removeClip(clipSelection, id) });
  }

  function clearAll() {
    if (!streamer) return;
    setPicked({ login: streamer.login, sel: emptySelection() });
  }

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
            <ReelSection
              key={`${streamer.login}|${selectedKey}`}
              login={streamer.login}
              range={rangeOfKey(selectedKey)}
              tick={tick}
              title={`Top clips - ${labelOfKey(selectedKey)}`}
              selection={clipSelection}
              onToggle={toggle}
              loadingNote={phase === "loading"}
              action={
                <button onClick={() => setSelection(null)} className="text-sm underline hover:text-zinc-200">
                  Clear
                </button>
              }
            />
          )}
          {reelList().map((r) => (
            <ReelSection
              key={`${streamer.login}|${r.key}`}
              login={streamer.login}
              range={r.range}
              tick={tick}
              title={r.title}
              selection={clipSelection}
              onToggle={toggle}
              loadingNote={phase === "loading"}
            />
          ))}
          {download.error && (
            <p className="rounded border border-red-900 bg-red-950 p-3 text-sm text-red-300">{download.error}</p>
          )}
          {download.job && <DownloadPanel state={download.job} />}
          <SelectionPanel
            selection={clipSelection}
            onRemove={remove}
            onClear={clearAll}
            onDownload={() => download.start(Array.from(clipSelection.values()))}
            downloading={download.downloading}
          />
        </>
      )}
    </main>
  );
}
