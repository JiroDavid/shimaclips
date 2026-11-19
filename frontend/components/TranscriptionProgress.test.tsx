// @vitest-environment jsdom
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import TranscriptionProgress from "@/components/TranscriptionProgress";
import type { Transcription } from "@/lib/api";
import { mockFetch } from "@/test/fetchMock";

const base: Transcription = { login: "newbie", display_name: "Newbie", state: "transcribing", total: 10, processed: 3, transcribed: 3, error: null };
const status = (over: Partial<Transcription>) => ({ ...base, ...over });

async function tick(ms = 2000) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

describe("TranscriptionProgress", () => {
  it("shows how far along the job is", () => {
    mockFetch([]);
    render(<TranscriptionProgress initial={base} onSearchAgain={() => {}} />);
    expect(screen.getByText("3 of 10 clips")).toBeTruthy();
    expect(screen.getByText("30%")).toBeTruthy();
    expect(screen.getByRole("progressbar").getAttribute("aria-valuenow")).toBe("30");
  });

  it("polls every two seconds, updates, and stops when it finishes", async () => {
    vi.useFakeTimers();
    const replies = [status({ processed: 6 }), status({ state: "done", processed: 10, transcribed: 10 })];
    const m = mockFetch([{ url: /\/transcribe$/, respond: () => replies.shift() ?? replies[0] }]);
    render(<TranscriptionProgress initial={base} onSearchAgain={() => {}} />);
    await tick();
    expect(screen.getByText("6 of 10 clips")).toBeTruthy();
    await tick();
    expect(screen.getByText("Done: 10 clips are searchable now.")).toBeTruthy();
    const calls = m.calls.length;
    await tick(10000);
    expect(m.calls.length).toBe(calls);
  });

  it("lets the user search again as soon as some clips are searchable", async () => {
    mockFetch([]);
    const again = vi.fn();
    render(<TranscriptionProgress initial={base} onSearchAgain={again} />);
    await userEvent.click(screen.getByRole("button", { name: "Search again" }));
    expect(again).toHaveBeenCalledOnce();
  });

  it("does not offer a search before anything is transcribed", () => {
    mockFetch([]);
    render(<TranscriptionProgress initial={status({ state: "finding", processed: 0, total: 0, transcribed: 0 })} onSearchAgain={() => {}} />);
    expect(screen.queryByRole("button", { name: "Search again" })).toBeNull();
    expect(screen.getByText("Finding their top clips from the last year...")).toBeTruthy();
  });

  it("shows an error and can retry", async () => {
    const m = mockFetch([{ method: "POST", url: /\/transcribe$/, respond: () => status({ state: "queued", processed: 0 }) }]);
    render(<TranscriptionProgress initial={status({ state: "error", error: "No clips were found." })} onSearchAgain={() => {}} />);
    expect(screen.getByText("No clips were found.")).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(m.count("POST", /transcribe$/)).toBe(1);
    expect(await screen.findByText("Waiting to start...")).toBeTruthy();
  });

  it("says when it loses contact with the server and keeps trying", async () => {
    vi.useFakeTimers();
    mockFetch([{ url: /\/transcribe$/, status: 500, respond: () => ({ detail: "down" }) }]);
    render(<TranscriptionProgress initial={base} onSearchAgain={() => {}} />);
    await tick();
    expect(screen.getByText("Lost contact with the server, retrying...")).toBeTruthy();
  });
});
