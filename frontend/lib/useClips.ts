"use client";

import { useEffect, useRef, useState } from "react";
import { getClips, type Clip } from "@/lib/api";
import { createLatest } from "@/lib/latest";

const PAGE = 10;
export const MAX_LIMIT = 100;
const NONE: Clip[] = [];

type Settled = { id: string; clips: Clip[]; total: number; error: string | null };

export function useClips(
  login: string | null,
  range: { start?: string; end?: string } | null,
  tick: number,
): { clips: Clip[]; total: number; loading: boolean; error: string | null; showMore(): void; hasMore: boolean; capped: boolean } {
  const [limit, setLimit] = useState(PAGE);
  const [settled, setSettled] = useState<Settled>({ id: "", clips: NONE, total: 0, error: null });
  const latest = useRef(createLatest());
  const start = range?.start;
  const end = range?.end;
  const enabled = !!login && range !== null;
  const id = `${login}|${start ?? ""}|${end ?? ""}|${limit}|${tick}`;

  useEffect(() => {
    if (!login || range === null) return;
    let cancelled = false;
    latest.current
      .run((signal) => getClips(login, { start, end, limit, offset: 0 }, signal))
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  if (!enabled) return { clips: NONE, total: 0, loading: false, error: null, showMore() {}, hasMore: false, capped: false };
  const capped = limit >= MAX_LIMIT && settled.total > MAX_LIMIT;
  return {
    clips: settled.clips,
    total: settled.total,
    loading: settled.id !== id,
    error: settled.error,
    showMore: () => setLimit((l) => Math.min(l + PAGE, MAX_LIMIT)),
    hasMore: settled.clips.length < settled.total && limit < MAX_LIMIT,
    capped,
  };
}
