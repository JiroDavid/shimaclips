"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { fileUrl, startDownload, watchJob, type Clip, type JobState } from "@/lib/api";

type Slot = { login: string; job: JobState | null; error: string | null; downloading: boolean };

export function useDownload(login: string | null) {
  const [slot, setSlot] = useState<Slot | null>(null);
  const downloadingRef = useRef(false);
  const runId = useRef(0);
  const stopWatching = useRef<(() => void) | null>(null);

  const cancel = useCallback(() => {
    runId.current += 1;
    stopWatching.current?.();
    stopWatching.current = null;
    downloadingRef.current = false;
    setSlot(null);
  }, []);

  useEffect(() => cancel, [login, cancel]);

  const start = useCallback(
    async (clips: Clip[]) => {
      if (!login || downloadingRef.current || clips.length === 0) return;
      downloadingRef.current = true;
      stopWatching.current?.();
      stopWatching.current = null;
      const run = ++runId.current;
      const patch = (p: Partial<Slot>) =>
        setSlot((prev) => ({ login, job: null, error: null, downloading: false, ...(prev?.login === login ? prev : {}), ...p }));
      patch({ job: null, error: null, downloading: true });
      try {
        const jobId = await startDownload(clips);
        if (run !== runId.current) return;
        patch({ job: { status: "running", error: null, items: [] } });
        let fired = false;
        stopWatching.current = watchJob(
          jobId,
          (state) => {
            if (run !== runId.current) return;
            patch({ job: state, downloading: state.status === "running" });
            if (state.status !== "running") downloadingRef.current = false;
            if (state.status === "done" && !fired) {
              fired = true;
              const a = document.createElement("a");
              a.href = fileUrl(jobId);
              document.body.appendChild(a);
              a.click();
              a.remove();
            }
          },
          () => {
            if (run !== runId.current) return;
            downloadingRef.current = false;
            patch({ job: null, error: "Lost connection to the downloader", downloading: false });
          },
        );
      } catch (err) {
        if (run !== runId.current) return;
        downloadingRef.current = false;
        patch({ error: err instanceof Error ? err.message : "Download failed", downloading: false });
      }
    },
    [login],
  );

  const current = slot && slot.login === login ? slot : null;
  return {
    job: current?.job ?? null,
    error: current?.error ?? null,
    downloading: current?.downloading ?? false,
    start,
  };
}
