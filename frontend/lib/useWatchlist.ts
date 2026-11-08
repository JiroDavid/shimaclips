"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  addWatch,
  getWatchlist,
  removeWatch,
  setWatchPaused,
  type WatchEntry,
} from "@/lib/api";
import { createLatest } from "@/lib/latest";

const POLL_MS = 5000;
const NO_PENDING: ReadonlySet<string> = new Set();

export function useWatchlist(): {
  entries: WatchEntry[];
  error: string | null;
  now: number;
  pending: ReadonlySet<string>;
  add(login: string): Promise<void>;
  remove(login: string): void;
  setPaused(login: string, paused: boolean): void;
} {
  const [entries, setEntries] = useState<WatchEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [now, setNow] = useState(0);
  const [pending, setPending] = useState<ReadonlySet<string>>(NO_PENDING);
  const latest = useRef(createLatest());
  const pendingRef = useRef(new Set<string>());
  const mounted = useRef(true);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const scheduleRef = useRef<() => void>(() => {});

  const refetch = useCallback(async () => {
    try {
      const res = await latest.current.run((signal) => getWatchlist(signal));
      if (!res.ok || !mounted.current) return;
      setEntries(res.value);
      setNow(Date.now());
      setError(null);
    } catch (e) {
      if (mounted.current) setError(e instanceof Error ? e.message : "Could not load the watchlist");
    }
  }, []);

  const schedule = useCallback(() => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(async () => {
      timer.current = null;
      await refetch();
      if (mounted.current) scheduleRef.current();
    }, POLL_MS);
  }, [refetch]);

  useEffect(() => {
    scheduleRef.current = schedule;
  }, [schedule]);

  useEffect(() => {
    mounted.current = true;
    const lat = latest.current;
    void refetch().then(() => {
      if (mounted.current) schedule();
    });
    return () => {
      mounted.current = false;
      lat.run(async () => undefined);
      if (timer.current) clearTimeout(timer.current);
      timer.current = null;
    };
  }, [refetch, schedule]);

  const act = useCallback(
    async (login: string, fn: () => Promise<unknown>) => {
      const key = login.toLowerCase();
      if (pendingRef.current.has(key)) return;
      pendingRef.current.add(key);
      setPending(new Set(pendingRef.current));
      try {
        await fn();
        setError(null);
      } catch (e) {
        if (mounted.current) setError(e instanceof Error ? e.message : "Watchlist update failed");
      }
      await refetch();
      pendingRef.current.delete(key);
      if (mounted.current) {
        setPending(new Set(pendingRef.current));
        schedule();
      }
    },
    [refetch, schedule],
  );

  const add = useCallback((login: string) => act(login, () => addWatch(login)), [act]);
  const remove = useCallback((login: string) => void act(login, () => removeWatch(login)), [act]);
  const setPaused = useCallback(
    (login: string, paused: boolean) => void act(login, () => setWatchPaused(login, paused)),
    [act],
  );

  return { entries, error, now, pending, add, remove, setPaused };
}
