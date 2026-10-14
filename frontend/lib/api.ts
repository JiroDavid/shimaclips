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

export function fileUrl(jobId: string): string {
  return `${API}/api/downloads/${jobId}/file`;
}
