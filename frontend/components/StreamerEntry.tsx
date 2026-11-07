"use client";

import { useState } from "react";

export default function StreamerEntry({ onSubmit }: { onSubmit: (login: string) => void }) {
  const [value, setValue] = useState("");

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const login = value.trim();
    if (!login) return;
    onSubmit(login);
  }

  return (
    <form onSubmit={submit} className="flex flex-wrap items-end gap-4 rounded-lg border border-zinc-800 bg-zinc-900 p-4">
      <label className="space-y-1 text-sm">
        <span className="block text-zinc-400">Streamer</span>
        <input
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="jasontheween"
          className="rounded bg-zinc-800 px-3 py-2"
        />
      </label>
      <button type="submit" className="rounded bg-purple-600 px-4 py-2 font-medium hover:bg-purple-500">
        Go
      </button>
    </form>
  );
}
