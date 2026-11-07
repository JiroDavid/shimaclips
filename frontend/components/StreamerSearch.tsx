"use client";

import { useEffect, useId, useRef, useState } from "react";
import { searchStreamers, type SearchHit } from "@/lib/api";
import { createLatest } from "@/lib/latest";
import { moveIndex } from "@/lib/searchNav";
import { useDebounced } from "@/lib/useDebounced";

const MAX_ROWS = 8;
const LOGIN_LIKE = /^@?[a-z0-9_]{1,25}$/i;

type Outcome = { q: string; results: SearchHit[]; error: string | null };

function Avatar({ hit }: { hit: SearchHit }) {
  const [failed, setFailed] = useState(false);
  if (failed || !hit.avatar_url) {
    return (
      <span
        aria-hidden
        className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-zinc-700 text-sm font-semibold uppercase"
      >
        {(hit.display_name || hit.login).charAt(0)}
      </span>
    );
  }
  return (
    <>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={hit.avatar_url}
        alt=""
        onError={() => setFailed(true)}
        className="h-8 w-8 shrink-0 rounded-full object-cover"
      />
    </>
  );
}

export default function StreamerSearch({ onSelect }: { onSelect: (login: string) => void }) {
  const listId = useId();
  const [text, setText] = useState("");
  const [open, setOpen] = useState(false);
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const [highlight, setHighlight] = useState<{ list: SearchHit[]; index: number } | null>(null);
  const [latest] = useState(() => createLatest());
  const alive = useRef(true);
  const root = useRef<HTMLDivElement>(null);

  const trimmed = text.trim();
  const debounced = useDebounced(trimmed, 250);
  const active = trimmed.length >= 2;

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  useEffect(() => {
    if (debounced.length < 2) return;
    latest
      .run((signal) => searchStreamers(debounced, signal))
      .then((res) => {
        if (!alive.current || !res.ok) return;
        setOutcome({ q: debounced, results: res.value, error: null });
      })
      .catch((e: unknown) => {
        if (!alive.current) return;
        setOutcome({ q: debounced, results: [], error: e instanceof Error ? e.message : "Search failed" });
      });
  }, [debounced, latest]);

  useEffect(() => {
    function onDocDown(e: MouseEvent) {
      if (root.current && !root.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDocDown);
    return () => document.removeEventListener("mousedown", onDocDown);
  }, []);

  const fresh = active && outcome !== null && outcome.q === trimmed ? outcome : null;
  const searching = active && fresh === null;
  const results = fresh ? fresh.results.slice(0, MAX_ROWS) : [];
  const error = fresh?.error ?? null;
  const index = highlight && highlight.list === fresh?.results ? highlight.index : -1;
  const showList = open && active;
  const optionId = (i: number) => `${listId}-opt-${i}`;

  function setIndex(i: number) {
    if (fresh) setHighlight({ list: fresh.results, index: i });
  }

  function select(login: string) {
    onSelect(login);
    setText("");
    setOutcome(null);
    setHighlight(null);
    setOpen(false);
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      setOpen(true);
      setIndex(moveIndex(index, e.key === "ArrowDown" ? 1 : -1, results.length));
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (results.length > 0) {
        select(results[index >= 0 ? index : 0].login);
      } else if (LOGIN_LIKE.test(trimmed)) {
        select(trimmed);
      }
    } else if (e.key === "Escape") {
      setOpen(false);
      setHighlight(null);
    }
  }

  return (
    <div ref={root} className="rounded-lg border border-zinc-800 bg-zinc-900 p-4">
      <label className="block space-y-1 text-sm">
        <span className="block text-zinc-400">Streamer</span>
        <div className="relative max-w-md">
          <input
            value={text}
            onChange={(e) => {
              setText(e.target.value);
              setOpen(true);
            }}
            onFocus={() => setOpen(true)}
            onBlur={() => setOpen(false)}
            onKeyDown={onKeyDown}
            placeholder="Search for a streamer"
            autoComplete="off"
            aria-label="Search for a streamer"
            role="combobox"
            aria-expanded={showList}
            aria-controls={listId}
            aria-autocomplete="list"
            aria-activedescendant={showList && index >= 0 ? optionId(index) : undefined}
            className="w-full rounded bg-zinc-800 px-3 py-2"
          />
          {showList && (
            <ul
              id={listId}
              role="listbox"
              className="absolute left-0 right-0 z-20 mt-1 overflow-hidden rounded border border-zinc-700 bg-zinc-900 shadow-lg"
            >
              {results.map((hit, i) => (
                <li
                  key={hit.login}
                  id={optionId(i)}
                  role="option"
                  aria-selected={i === index}
                  onMouseDown={(e) => {
                    e.preventDefault();
                    select(hit.login);
                  }}
                  onMouseEnter={() => setIndex(i)}
                  className={`flex cursor-pointer items-center gap-3 border-l-2 px-3 py-2 hover:bg-zinc-800 ${
                    i === index ? "border-purple-500 bg-zinc-800" : "border-transparent"
                  }`}
                >
                  <Avatar hit={hit} />
                  <span className="min-w-0 truncate font-bold">{hit.display_name}</span>
                  {hit.display_name.toLowerCase() !== hit.login.toLowerCase() && (
                    <span className="min-w-0 truncate text-zinc-400">{hit.login}</span>
                  )}
                  {hit.is_live && (
                    <span className="ml-auto flex items-center">
                      <span className="h-2 w-2 rounded-full bg-green-500" aria-hidden />
                      <span className="sr-only">live</span>
                    </span>
                  )}
                </li>
              ))}
              {fresh && !error && results.length === 0 && (
                <li role="presentation" className="px-3 py-2 text-zinc-400">
                  No matches
                </li>
              )}
            </ul>
          )}
        </div>
      </label>
      {searching && open && <p className="mt-1 text-xs text-zinc-400">Searching...</p>}
      {error && <p className="mt-1 text-xs text-red-400">{error}</p>}
    </div>
  );
}
