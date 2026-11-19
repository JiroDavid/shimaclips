// @vitest-environment jsdom
import { StrictMode, useEffect, useRef } from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useStreamer } from "@/lib/useStreamer";
import { mockFetch } from "@/test/fetchMock";

const loaded = {
  streamer: { login: "yugi2x", display_name: "Yugi2x", account_created: "2023-07-24T00:00:00Z" },
  state: { status: "done", error: null, windows_done: 1, windows_total: 1, clips: 10, capped: 0, started_at: 1 },
};

function ArrivesFromTheUrl({ login }: { login: string }) {
  const s = useStreamer();
  const open = useRef(s.open);
  useEffect(() => {
    open.current = s.open;
  });
  useEffect(() => {
    open.current(login);
  }, [login]);
  return <p>{`${s.phase}:${s.streamer?.display_name ?? "nobody"}`}</p>;
}

describe("useStreamer", () => {
  it("still opens the streamer when React mounts, unmounts and remounts the page in development", async () => {
    mockFetch([{ method: "POST", url: /\/api\/streamers\/yugi2x\/load/, respond: () => loaded }]);
    render(
      <StrictMode>
        <ArrivesFromTheUrl login="yugi2x" />
      </StrictMode>,
    );
    expect(await screen.findByText("ready:Yugi2x")).toBeTruthy();
  });

  it("ignores a repeated request for the streamer that is already opening", async () => {
    const m = mockFetch([{ method: "POST", url: /\/load/, respond: () => loaded }]);
    function Twice() {
      const s = useStreamer();
      useEffect(() => {
        s.open("yugi2x");
        s.open("YUGI2X");
        // eslint-disable-next-line react-hooks/exhaustive-deps
      }, []);
      return <p>{s.phase}</p>;
    }
    render(<Twice />);
    expect(await screen.findByText("ready")).toBeTruthy();
    expect(m.count("POST", /\/load/)).toBe(1);
  });

  it("reports a failed load instead of hanging", async () => {
    mockFetch([{ method: "POST", url: /\/load/, status: 404, respond: () => ({ detail: "Streamer 'x' not found" }) }]);
    function Probe() {
      const s = useStreamer();
      useEffect(() => {
        s.open("x");
        // eslint-disable-next-line react-hooks/exhaustive-deps
      }, []);
      return <p>{`${s.phase}:${s.error ?? ""}`}</p>;
    }
    render(<Probe />);
    expect(await screen.findByText("error:Streamer 'x' not found")).toBeTruthy();
  });
});
