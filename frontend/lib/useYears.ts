"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { getYears, setYearExact, type YearInfo } from "@/lib/api";
import { createLatest } from "@/lib/latest";

const NONE: YearInfo[] = [];
const NO_PENDING: ReadonlySet<number> = new Set();

type Settled = { login: string; years: YearInfo[]; error: string | null };
type ToggleError = { login: string; error: string };
type Pending = { login: string; years: ReadonlySet<number> };

export function useYears(
  login: string | null,
  tick: number,
): {
  years: YearInfo[];
  error: string | null;
  pending: ReadonlySet<number>;
  toggle(year: number, enabled: boolean, onApplied?: () => void): void;
  reload(): void;
} {
  const [settled, setSettled] = useState<Settled>({ login: "", years: NONE, error: null });
  const [pendingState, setPendingState] = useState<Pending>({ login: "", years: NO_PENDING });
  const [toggleError, setToggleError] = useState<ToggleError | null>(null);
  const [reloads, setReloads] = useState(0);
  const latest = useRef(createLatest());
  const pendingRef = useRef(new Set<string>());
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  useEffect(() => {
    if (!login) return;
    let cancelled = false;
    latest.current
      .run((signal) => getYears(login, signal))
      .then((res) => {
        if (cancelled || !res.ok) return;
        setSettled({ login, years: res.value, error: null });
      })
      .catch((e) => {
        if (cancelled) return;
        const error = e instanceof Error ? e.message : "Could not load years";
        setSettled((prev) => ({ login, years: prev.login === login ? prev.years : NONE, error }));
      });
    return () => {
      cancelled = true;
    };
  }, [login, tick, reloads]);

  const syncPending = useCallback((forLogin: string) => {
    const prefix = `${forLogin}|`;
    const years = new Set<number>();
    pendingRef.current.forEach((k) => {
      if (k.startsWith(prefix)) years.add(Number(k.slice(prefix.length)));
    });
    setPendingState({ login: forLogin, years });
  }, []);

  const toggle = useCallback(
    (year: number, enabled: boolean, onApplied?: () => void) => {
      if (!login) return;
      const key = `${login}|${year}`;
      if (pendingRef.current.has(key)) return;
      pendingRef.current.add(key);
      setToggleError(null);
      syncPending(login);
      (async () => {
        let error: string | null = null;
        try {
          await setYearExact(login, year, enabled);
        } catch (e) {
          error = e instanceof Error ? e.message : "Could not update the year";
        }
        if (!error) {
          if (mounted.current) onApplied?.();
          try {
            const res = await latest.current.run((signal) => getYears(login, signal));
            if (res.ok && mounted.current) setSettled({ login, years: res.value, error: null });
          } catch {}
        }
        pendingRef.current.delete(key);
        if (!mounted.current) return;
        syncPending(login);
        if (error) setToggleError({ login, error });
        setReloads((n) => n + 1);
      })();
    },
    [login, syncPending],
  );

  const reload = useCallback(() => setReloads((n) => n + 1), []);

  const mine = login !== null && settled.login === login;
  return {
    years: mine ? settled.years : NONE,
    error: toggleError?.login === login ? toggleError.error : mine ? settled.error : null,
    pending: login !== null && pendingState.login === login ? pendingState.years : NO_PENDING,
    toggle,
    reload,
  };
}
