"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import Logo from "@/components/Logo";
import StreamerSearch from "@/components/StreamerSearch";
import type { ConversationSummary } from "@/lib/api";

const ICON = "h-5 w-5 shrink-0";

function PlusIcon() {
  return (
    <svg viewBox="0 0 24 24" className={ICON} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden>
      <path d="M12 5v14M5 12h14" />
    </svg>
  );
}

function CalendarIcon() {
  return (
    <svg viewBox="0 0 24 24" className={ICON} fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <rect x="3.5" y="5" width="17" height="15" rx="2.5" />
      <path d="M3.5 10h17M8 3v4M16 3v4" />
    </svg>
  );
}

function PanelIcon() {
  return (
    <svg viewBox="0 0 24 24" className={ICON} fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <rect x="3.5" y="4.5" width="17" height="15" rx="2.5" />
      <path d="M9.5 4.5v15" />
    </svg>
  );
}

const ROW = "flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-sm hover:bg-zinc-900";

export default function Sidebar({
  open,
  onToggle,
  conversations,
  activeId,
  error,
  onNew,
  onOpen,
  onDelete,
}: {
  open: boolean;
  onToggle: () => void;
  conversations: ConversationSummary[];
  activeId: string | null;
  error: string | null;
  onNew: () => void;
  onOpen: (id: string) => void;
  onDelete: (id: string) => void;
}) {
  const router = useRouter();
  const [lookupOpen, setLookupOpen] = useState(false);

  if (!open) {
    return (
      <nav aria-label="Sidebar" className="sticky top-0 flex h-screen w-14 shrink-0 flex-col items-center gap-2 border-r border-zinc-800 py-3">
        <button onClick={onNew} aria-label="Shimaclips, start a new chat" className="rounded-lg p-1 hover:bg-zinc-900">
          <Logo className="h-8 w-8" />
        </button>
        <button onClick={onToggle} aria-label="Open sidebar" className="rounded-lg p-2 text-zinc-400 hover:bg-zinc-900 hover:text-zinc-50">
          <PanelIcon />
        </button>
        <button onClick={onNew} aria-label="New chat" className="rounded-lg p-2 text-zinc-400 hover:bg-zinc-900 hover:text-zinc-50">
          <PlusIcon />
        </button>
      </nav>
    );
  }

  return (
    <nav aria-label="Sidebar" className="sticky top-0 flex h-screen w-64 shrink-0 flex-col border-r border-zinc-800 bg-zinc-950">
      <div className="flex items-center justify-between px-3 py-3">
        <button onClick={onNew} aria-label="Shimaclips, start a new chat" className="flex items-center gap-2 rounded-lg px-1 py-1 hover:bg-zinc-900">
          <Logo className="h-8 w-8" />
          <span className="text-lg font-semibold tracking-tight">Shimaclips</span>
        </button>
        <button onClick={onToggle} aria-label="Close sidebar" className="rounded-lg p-2 text-zinc-400 hover:bg-zinc-900 hover:text-zinc-50">
          <PanelIcon />
        </button>
      </div>

      <div className="space-y-1 px-2">
        <button onClick={onNew} className={ROW}>
          <PlusIcon />
          New chat
        </button>
        <button onClick={() => setLookupOpen((v) => !v)} aria-expanded={lookupOpen} className={ROW}>
          <CalendarIcon />
          Browse calendar
        </button>
        {lookupOpen && (
          <div className="px-1 pb-1">
            <StreamerSearch onSelect={(login) => router.push(`/browse?streamer=${encodeURIComponent(login)}`)} />
          </div>
        )}
      </div>

      <p className="px-5 pb-1 pt-6 text-xs text-zinc-500">Recents</p>
      <ul className="min-h-0 flex-1 space-y-0.5 overflow-y-auto px-2 pb-3">
        {conversations.map((c) => (
          <li key={c.id} className="group relative">
            <button
              onClick={() => onOpen(c.id)}
              aria-current={c.id === activeId ? "page" : undefined}
              title={c.title}
              className={`block w-full truncate rounded-lg py-2 pl-3 pr-9 text-left text-sm hover:bg-zinc-900 ${
                c.id === activeId ? "bg-zinc-800" : "text-zinc-300"
              }`}
            >
              {c.title}
            </button>
            <button
              onClick={() => onDelete(c.id)}
              aria-label={`Delete chat: ${c.title}`}
              className="absolute right-1.5 top-1/2 hidden -translate-y-1/2 rounded-md p-1 text-zinc-400 hover:bg-zinc-700 hover:text-zinc-50 focus:block group-focus-within:block group-hover:block"
            >
              <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden>
                <path d="M6 6l12 12M18 6L6 18" />
              </svg>
            </button>
          </li>
        ))}
        {conversations.length === 0 && !error && <li className="px-3 py-2 text-xs text-zinc-500">Your chats will appear here.</li>}
        {error && <li className="px-3 py-2 text-xs text-red-400">{error}</li>}
      </ul>
      <p className="border-t border-zinc-800 px-5 py-3 text-xs text-zinc-500">Saved on this computer</p>
    </nav>
  );
}
