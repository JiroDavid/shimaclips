"use client";

import { useEffect, useRef, useState } from "react";
import { getCalendar, type Bucket } from "@/lib/api";
import { createLatest } from "@/lib/latest";
import { useGatedTick } from "@/lib/useGatedTick";

const NONE: Bucket[] = [];

type Settled = { id: string; base: string; buckets: Bucket[]; error: string | null };

export function useCalendar(
  login: string | null,
  granularity: "month" | "day",
  start: string,
  end: string,
  tick: number,
): { buckets: Bucket[]; loading: boolean; error: string | null } {
  const [settled, setSettled] = useState<Settled>({ id: "", base: "", buckets: NONE, error: null });
  const latest = useRef(createLatest());
  const base = `${login}|${granularity}|${start}|${end}`;
  const gated = useGatedTick(tick, (g) => settled.id !== `${base}|${g}`);
  const id = `${base}|${gated}`;

  useEffect(() => {
    if (!login) return;
    let cancelled = false;
    latest.current
      .run((signal) => getCalendar(login, granularity, start, end, signal))
      .then((res) => {
        if (cancelled || !res.ok) return;
        setSettled({ id, base, buckets: res.value, error: null });
      })
      .catch((e) => {
        if (cancelled) return;
        const error = e instanceof Error ? e.message : "Could not load calendar";
        setSettled((prev) => ({ id, base, buckets: prev.buckets, error }));
      });
    return () => {
      cancelled = true;
    };
  }, [login, granularity, start, end, gated, id, base]);

  if (!login) return { buckets: NONE, loading: false, error: null };
  return { buckets: settled.buckets, loading: settled.base !== base, error: settled.error };
}
