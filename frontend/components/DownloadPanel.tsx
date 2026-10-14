import type { JobState } from "@/lib/api";

export default function DownloadPanel({ state }: { state: JobState }) {
  return (
    <div className="space-y-2 rounded-lg border border-zinc-800 bg-zinc-900 p-4">
      <p className="text-sm font-medium">
        {state.status === "running" && "Downloading clips..."}
        {state.status === "done" && "Done - your browser download should start now"}
        {state.status === "error" && `Failed: ${state.error}`}
      </p>
      <ul className="space-y-1 text-xs">
        {state.items.map((item) => (
          <li key={item.name} className="flex items-center justify-between gap-3">
            <span className="truncate text-zinc-300">{item.name}</span>
            <span className={item.status === "failed" ? "text-red-400" : "text-zinc-400"}>
              {item.status === "downloading" && `${Math.round(item.percent)}%`}
              {item.status === "done" && "done"}
              {item.status === "pending" && "waiting"}
              {item.status === "failed" && `failed: ${item.error}`}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
