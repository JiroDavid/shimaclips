"use client";

import { useEffect, useRef, useState } from "react";
import { getClips, type Clip } from "@/lib/api";
import { createLatest } from "@/lib/latest";
import { appendUnique, nextPage } from "@/lib/paging";

const PAGE = 10;
const NONE: Clip[] = [];

type Settled = { id: string; clips: Clip[]; total: number; error: string | null };

async function fetchTop(
  login: string,
  start: string | undefined,
  end: string | undefined,
  limit: number,
  signal: AbortSignal,
): Promise<{ clips: Clip[]; total: number }> {
  let clips: Clip[] = [];
  let fetched = 0;
  let total: number | null = null;
  for (let page = nextPage(0, limit, null); page; page = nextPage(fetched, limit, total)) {
    if (signal.aborted) throw new DOMException("Aborted", "AbortError");
    const res = await getClips(login, { start, end, ...page }, signal);
    total = res.total;
    fetched += res.clips.length;
    clips = appendUnique(clips, res.clips);
    if (res.clips.length === 0) break;
  }
  return { clips, total: total ?? 0 };
}

export function useClips(
  login: string | null,
  range: { start?: string; end?: string } | null,
  tick: number,
): { clips: Clip[]; total: number; loading: boolean; error: string | null; showMore(): void; hasMore: boolean } {
  const [limit, setLimit] = useState(PAGE);
  const [settled, setSettled] = useState<Settled>({ id: "", clips: NONE, total: 0, error: null });
  const latest = useRef(createLatest());
  const start = range?.start;
  const end = range?.end;
  const enabled = !!login && range !== null;
  const id = `${enabled}|${login}|${start ?? ""}|${end ?? ""}|${limit}|${tick}`;

  useEffect(() => {
    if (!enabled || !login) return;
    let cancelled = false;
    latest.current
      .run((signal) => fetchTop(login, start, end, limit, signal))
      .then((res) => {
        if (cancelled || !res.ok) return;
        setSettled({ id, clips: res.value.clips, total: res.value.total, error: null });
      })
      .catch((e) => {
        if (cancelled) return;
        const error = e instanceof Error ? e.message : "Could not load clips";
        setSettled((prev) => ({ ...prev, id, error }));
      });
    return () => {
      cancelled = true;
    };
  }, [enabled, login, start, end, limit, tick, id]);

  if (!enabled) return { clips: NONE, total: 0, loading: false, error: null, showMore() {}, hasMore: false };
  return {
    clips: settled.clips,
    total: settled.total,
    loading: settled.id !== id,
    error: settled.error,
    showMore: () => setLimit((l) => l + PAGE),
    hasMore: settled.clips.length < settled.total,
  };
}
