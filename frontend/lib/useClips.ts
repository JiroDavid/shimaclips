"use client";

import { useEffect, useRef, useState } from "react";
import { getClips, type Clip } from "@/lib/api";
import { createLatest } from "@/lib/latest";
import type { Sort } from "@/lib/sort";
import { appendUnique, nextPage } from "@/lib/paging";

const PAGE = 10;
const NONE: Clip[] = [];

type Settled = { id: string; clips: Clip[]; total: number; exact: boolean; hasMore: boolean; error: string | null };

async function fetchTop(
  login: string,
  start: string | undefined,
  end: string | undefined,
  limit: number,
  sort: Sort,
  signal: AbortSignal,
): Promise<{ clips: Clip[]; total: number; exact: boolean; hasMore: boolean }> {
  let clips: Clip[] = [];
  let fetched = 0;
  let total = 0;
  let exact = false;
  let hasMore: boolean | null = null;
  for (let page = nextPage(0, limit, null); page; page = nextPage(fetched, limit, hasMore)) {
    if (signal.aborted) throw new DOMException("Aborted", "AbortError");
    const res = await getClips(login, { start, end, sort, ...page }, signal);
    total = res.total;
    exact = res.exact;
    hasMore = res.has_more && res.clips.length > 0;
    fetched += res.clips.length;
    clips = appendUnique(clips, res.clips);
    if (res.clips.length === 0) break;
  }
  return { clips, total, exact, hasMore: hasMore === true };
}

export function useClips(
  login: string | null,
  range: { start?: string; end?: string } | null,
  tick: number,
  sort: Sort = "views",
): {
  clips: Clip[];
  total: number;
  exact: boolean;
  loading: boolean;
  error: string | null;
  showMore(): void;
  hasMore: boolean;
} {
  const [limit, setLimit] = useState(PAGE);
  const [settled, setSettled] = useState<Settled>({ id: "", clips: NONE, total: 0, exact: false, hasMore: false, error: null });
  const latest = useRef(createLatest());
  const start = range?.start;
  const end = range?.end;
  const enabled = !!login && range !== null;
  const id = `${enabled}|${login}|${start ?? ""}|${end ?? ""}|${sort}|${limit}|${tick}`;

  useEffect(() => {
    if (!enabled || !login) return;
    let cancelled = false;
    latest.current
      .run((signal) => fetchTop(login, start, end, limit, sort, signal))
      .then((res) => {
        if (cancelled || !res.ok) return;
        setSettled({ id, clips: res.value.clips, total: res.value.total, exact: res.value.exact, hasMore: res.value.hasMore, error: null });
      })
      .catch((e) => {
        if (cancelled) return;
        const error = e instanceof Error ? e.message : "Could not load clips";
        setSettled((prev) => ({ ...prev, id, error }));
      });
    return () => {
      cancelled = true;
    };
  }, [enabled, login, start, end, sort, limit, tick, id]);

  if (!enabled) return { clips: NONE, total: 0, exact: false, loading: false, error: null, showMore() {}, hasMore: false };
  return {
    clips: settled.clips,
    total: settled.total,
    exact: settled.exact,
    loading: settled.id !== id,
    error: settled.error,
    showMore: () => setLimit((l) => l + PAGE),
    hasMore: settled.hasMore,
  };
}
