"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { loadStreamer, watchStreamer, type LoadState, type Streamer } from "@/lib/api";
import { createLatest } from "@/lib/latest";

export type Phase = "idle" | "opening" | "loading" | "ready" | "error";

const TICK_INTERVAL_MS = 2000;

export function useStreamer() {
  const [streamer, setStreamer] = useState<Streamer | null>(null);
  const [state, setState] = useState<LoadState | null>(null);
  const [phase, setPhaseState] = useState<Phase>("idle");
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  const phaseRef = useRef<Phase>("idle");
  const loginRef = useRef<string | null>(null);
  const openId = useRef(0);
  const closeStream = useRef<(() => void) | null>(null);
  const latest = useRef(createLatest());
  const lastTickAt = useRef(0);
  const lastClips = useRef(-1);
  const lastDone = useRef(-1);
  const lastTotal = useRef(-1);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const setPhase = useCallback((p: Phase) => {
    phaseRef.current = p;
    setPhaseState(p);
  }, []);

  const clearTimer = useCallback(() => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
  }, []);

  const stop = useCallback(() => {
    closeStream.current?.();
    closeStream.current = null;
    clearTimer();
  }, [clearTimer]);

  const bump = useCallback(() => {
    clearTimer();
    lastTickAt.current = Date.now();
    setTick((t) => t + 1);
  }, [clearTimer]);

  const apply = useCallback(
    (id: number, s: LoadState) => {
      setState(s);
      if (s.status === "queued" || s.status === "running") {
        setPhase("loading");
        if (
          s.clips === lastClips.current &&
          s.windows_done === lastDone.current &&
          s.windows_total === lastTotal.current
        )
          return;
        lastClips.current = s.clips;
        lastDone.current = s.windows_done;
        lastTotal.current = s.windows_total;
        const wait = lastTickAt.current + TICK_INTERVAL_MS - Date.now();
        if (wait <= 0) bump();
        else if (!timer.current) {
          timer.current = setTimeout(() => {
            if (id === openId.current) bump();
          }, wait);
        }
        return;
      }
      lastClips.current = s.clips;
      lastDone.current = s.windows_done;
      lastTotal.current = s.windows_total;
      if (s.status === "done") {
        setError(null);
        setPhase("ready");
      } else {
        setError(s.error ?? "Loading failed");
        setPhase("error");
      }
      bump();
    },
    [bump, setPhase],
  );

  const run = useCallback(
    async (login: string, mode: "auto" | "full", keepStreamer: boolean) => {
      const id = ++openId.current;
      stop();
      loginRef.current = login;
      lastClips.current = -1;
      lastDone.current = -1;
      lastTotal.current = -1;
      lastTickAt.current = 0;
      if (!keepStreamer) setStreamer(null);
      setState(null);
      setError(null);
      setPhase("opening");
      try {
        const res = await latest.current.run((signal) => loadStreamer(login, mode, signal));
        if (!res.ok || id !== openId.current) return;
        const { streamer: st, state: s } = res.value;
        loginRef.current = st.login;
        setStreamer(st);
        apply(id, s);
        if (s.status === "done" || s.status === "error") return;
        closeStream.current = watchStreamer(
          st.login,
          (next) => {
            if (id === openId.current) apply(id, next);
          },
          () => {
            if (id !== openId.current) return;
            stop();
            setError("Lost connection to the loader");
            setPhase("error");
          },
        );
      } catch (e) {
        if (id !== openId.current) return;
        setError(e instanceof Error ? e.message : "Could not load streamer");
        setPhase("error");
      }
    },
    [apply, setPhase, stop],
  );

  const open = useCallback(
    (raw: string) => {
      const login = raw.trim();
      if (!login) return;
      const busy = phaseRef.current === "opening" || phaseRef.current === "loading";
      if (busy && loginRef.current?.toLowerCase() === login.toLowerCase()) return;
      void run(login, "auto", false);
    },
    [run],
  );

  const refresh = useCallback(
    (full: boolean) => {
      if (!loginRef.current) return;
      void run(loginRef.current, full ? "full" : "auto", true);
    },
    [run],
  );

  const reattach = useCallback(() => {
    const login = loginRef.current;
    if (!login || phaseRef.current === "opening") return;
    const id = openId.current;
    stop();
    lastClips.current = -1;
    lastDone.current = -1;
    lastTotal.current = -1;
    closeStream.current = watchStreamer(
      login,
      (next) => {
        if (id === openId.current) apply(id, next);
      },
      () => {
        if (id !== openId.current) return;
        stop();
        setError("Lost connection to the loader");
        setPhase("error");
      },
    );
  }, [apply, setPhase, stop]);

  const dispose = useCallback(() => {
    openId.current++;
    stop();
  }, [stop]);

  useEffect(() => dispose, [dispose]);

  return {
    streamer,
    state,
    phase,
    error,
    tick,
    startedAt: state ? state.started_at * 1000 : null,
    open,
    refresh,
    reattach,
  };
}
