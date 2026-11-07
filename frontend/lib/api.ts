export const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Clip = {
  id: string;
  url: string;
  title: string;
  thumbnail_url: string;
  view_count: number;
  duration: number;
  creator_name: string;
  created_at: string;
};

export type JobItem = {
  name: string;
  status: "pending" | "downloading" | "done" | "failed";
  percent: number;
  error: string | null;
};

export type JobState = {
  status: "running" | "done" | "error";
  error: string | null;
  items: JobItem[];
};

export type SearchBody = {
  streamer: string;
  count: number;
  month?: string;
  start?: string;
  end?: string;
};

async function errorMessage(r: Response): Promise<string> {
  try {
    const body = await r.json();
    if (typeof body.detail === "string") return body.detail;
    if (Array.isArray(body.detail)) {
      return body.detail.map((d: { msg: string }) => d.msg.replace(/^Value error, /, "")).join("; ");
    }
  } catch {}
  return `Request failed (${r.status})`;
}

export async function searchClips(body: SearchBody): Promise<{ clips: Clip[]; total_in_window: number }> {
  const r = await fetch(`${API}/api/clips/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(await errorMessage(r));
  return r.json();
}

export async function startDownload(clips: Clip[]): Promise<string> {
  const r = await fetch(`${API}/api/downloads`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      clips: clips.map((c) => ({ url: c.url, title: c.title, view_count: c.view_count })),
    }),
  });
  if (!r.ok) throw new Error(await errorMessage(r));
  return (await r.json()).job_id;
}

export function watchJob(jobId: string, onUpdate: (s: JobState) => void): () => void {
  const es = new EventSource(`${API}/api/downloads/${jobId}/events`);
  es.onmessage = (e) => {
    const state: JobState = JSON.parse(e.data);
    onUpdate(state);
    if (state.status !== "running") es.close();
  };
  es.onerror = () => es.close();
  return () => es.close();
}

export type Streamer = {
  login: string;
  display_name: string;
  account_created: string;
};

export type LoadState = {
  status: "queued" | "running" | "done" | "error";
  error: string | null;
  windows_done: number;
  windows_total: number;
  clips: number;
  capped: boolean;
  started_at: number;
};

export type Bucket = { key: string; count: number; ready: boolean };

export async function loadStreamer(
  login: string,
  mode: "auto" | "full" = "auto",
  signal?: AbortSignal,
): Promise<{ streamer: Streamer; state: LoadState }> {
  const r = await fetch(`${API}/api/streamers/${encodeURIComponent(login)}/load?mode=${mode}`, {
    method: "POST",
    signal,
  });
  if (!r.ok) throw new Error(await errorMessage(r));
  return r.json();
}

export function watchStreamer(login: string, onUpdate: (s: LoadState) => void): () => void {
  const es = new EventSource(`${API}/api/streamers/${encodeURIComponent(login)}/events`);
  es.onmessage = (e) => {
    const state: LoadState = JSON.parse(e.data);
    onUpdate(state);
    if (state.status === "done" || state.status === "error") es.close();
  };
  es.onerror = () => es.close();
  return () => es.close();
}

export async function getCalendar(
  login: string,
  granularity: "month" | "day",
  start: string,
  end: string,
  signal?: AbortSignal,
): Promise<Bucket[]> {
  const q = new URLSearchParams({ granularity, start, end });
  const r = await fetch(`${API}/api/streamers/${encodeURIComponent(login)}/calendar?${q}`, { signal });
  if (!r.ok) throw new Error(await errorMessage(r));
  return (await r.json()).buckets;
}

export async function getClips(
  login: string,
  params: { start?: string; end?: string; limit: number; offset: number },
  signal?: AbortSignal,
): Promise<{ clips: Clip[]; total: number }> {
  const q = new URLSearchParams({ limit: String(params.limit), offset: String(params.offset) });
  if (params.start) q.set("start", params.start);
  if (params.end) q.set("end", params.end);
  const r = await fetch(`${API}/api/streamers/${encodeURIComponent(login)}/clips?${q}`, { signal });
  if (!r.ok) throw new Error(await errorMessage(r));
  return r.json();
}

export function fileUrl(jobId: string): string {
  return `${API}/api/downloads/${jobId}/file`;
}
