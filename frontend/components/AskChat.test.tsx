// @vitest-environment jsdom
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import AskChat from "@/components/AskChat";
import type { AskResult, Clip } from "@/lib/api";
import { mockFetch } from "@/test/fetchMock";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

const clip = (id: string, views: number): Clip => ({
  id, url: `https://clips.twitch.tv/${id}`, title: `Clip ${id}`, thumbnail_url: `https://t/${id}.jpg`,
  view_count: views, duration: 30, creator_name: "fan", created_at: "2026-10-01T00:00:00Z",
});

const result = (over: Partial<AskResult> = {}): AskResult => ({
  question: "q", kind: "answer", answer: "Here are the top 2 clips for Jay.", after: "This period isn't fully loaded yet.",
  streamer: { login: "jay", display_name: "Jay" }, suggestions: [], tool: "top_clips", sources: [clip("a", 900), clip("b", 100)],
  web_sources: [], months: [], confident: true, usage: { prompt_tokens: 5, output_tokens: 5 }, seconds: 1.2, conversation_id: "conv1", ...over,
});

type Chat = { id: string; title: string; turns: { question: string; result: AskResult }[] };

function backend(initial: Chat[] = [], nextResult: () => AskResult | { status: number; detail: string } = () => result()) {
  const chats = [...initial];
  const m = mockFetch([
    { url: /\/api\/conversations$/, respond: () => ({ conversations: chats.map((c) => ({ id: c.id, title: c.title, updated_at: "x" })) }) },
    { url: /\/api\/conversations\/[^/]+$/, respond: ({ url }) => chats.find((c) => url.endsWith(c.id)) },
    { method: "DELETE", url: /\/api\/conversations\/[^/]+$/, respond: ({ url }) => {
      chats.splice(chats.findIndex((c) => url.endsWith(c.id)), 1);
      return { ok: true };
    } },
    { method: "POST", url: /\/api\/ask$/, respond: ({ body }) => {
      const out = nextResult();
      if ("status" in out) return { detail: out.detail };
      const q = (body as { question: string }).question;
      const id = (body as { conversation_id: string | null }).conversation_id ?? out.conversation_id!;
      const existing = chats.find((c) => c.id === id);
      if (existing) existing.turns.push({ question: q, result: out });
      else chats.unshift({ id, title: q, turns: [{ question: q, result: out }] });
      return { ...out, conversation_id: id };
    } },
    { method: "POST", url: /\/api\/downloads$/, respond: () => ({ job_id: "job1" }) },
  ]);
  return { m, chats };
}

async function ask(text: string) {
  await userEvent.type(screen.getByLabelText(/Ask a question/), text);
  await userEvent.click(screen.getByRole("button", { name: "Ask" }));
}

beforeEach(() => {
  vi.stubGlobal("confirm", vi.fn(() => true));
  vi.stubGlobal("EventSource", class { close() {} onmessage = null; onerror = null; });
});

describe("AskChat", () => {
  it("opens on a welcome screen with generic examples that do not assume a streamer", async () => {
    backend();
    render(<AskChat />);
    expect(screen.getByText("What clips are you after?")).toBeTruthy();
    const chips = screen.getAllByRole("button").filter((b) => /^(Top|How many)/.test(b.textContent ?? ""));
    expect(chips.length).toBe(4);
    expect(chips.some((c) => /jasontheween/i.test(c.textContent ?? ""))).toBe(false);
  });

  it("answers in order: lead text, then the clips, then the follow-up text", async () => {
    backend();
    render(<AskChat />);
    await ask("top 2 clips for jay");
    expect(await screen.findByText("Here are the top 2 clips for Jay.")).toBeTruthy();
    const lead = screen.getByText("Here are the top 2 clips for Jay.");
    const first = screen.getByText("Clip a");
    const after = screen.getByText("This period isn't fully loaded yet.");
    expect(lead.compareDocumentPosition(first) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(first.compareDocumentPosition(after) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.getByText(/top_clips - 1.2s/)).toBeTruthy();
  });

  it("saves the chat to the sidebar and keeps the conversation and streamer for follow-ups", async () => {
    const { m } = backend();
    render(<AskChat />);
    await ask("top 2 clips for jay");
    await screen.findByText("Here are the top 2 clips for Jay.");
    expect(await within(screen.getByRole("navigation")).findByText("top 2 clips for jay")).toBeTruthy();
    expect(m.calls.find((c) => c.method === "POST" && /ask$/.test(c.url))!.body).toMatchObject({ login: null, conversation_id: null });

    await ask("and the newest ones");
    await waitFor(() => expect(m.calls.filter((c) => /ask$/.test(c.url)).length).toBe(2));
    const second = m.calls.filter((c) => /ask$/.test(c.url))[1].body;
    expect(second).toMatchObject({ login: "jay", conversation_id: "conv1" });
  });

  it("starts a fresh chat from New chat and reopens an old one from the sidebar", async () => {
    const old: Chat = { id: "old1", title: "Earlier question", turns: [{ question: "Earlier question", result: result({ answer: "An earlier answer.", conversation_id: "old1" }) }] };
    backend([old]);
    render(<AskChat />);
    await userEvent.click(await screen.findByText("Earlier question"));
    expect(await screen.findByText("An earlier answer.")).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: "New chat" }));
    expect(screen.getByText("What clips are you after?")).toBeTruthy();
    expect(screen.queryByText("An earlier answer.")).toBeNull();
  });

  it("deletes a chat after confirmation and returns to the welcome screen when it was open", async () => {
    const old: Chat = { id: "old1", title: "Earlier question", turns: [{ question: "Earlier question", result: result({ answer: "An earlier answer.", conversation_id: "old1" }) }] };
    const { m } = backend([old]);
    render(<AskChat />);
    await userEvent.click(await screen.findByText("Earlier question"));
    await screen.findByText("An earlier answer.");
    await userEvent.click(screen.getByRole("button", { name: "Delete chat: Earlier question" }));
    await waitFor(() => expect(m.count("DELETE", /old1$/)).toBe(1));
    expect(await screen.findByText("What clips are you after?")).toBeTruthy();
    expect(screen.queryByText("Earlier question")).toBeNull();
  });

  it("does not delete when the user cancels the confirmation", async () => {
    vi.stubGlobal("confirm", vi.fn(() => false));
    const old: Chat = { id: "old1", title: "Earlier question", turns: [{ question: "Earlier question", result: result({ conversation_id: "old1" }) }] };
    const { m } = backend([old]);
    render(<AskChat />);
    await screen.findByText("Earlier question");
    await userEvent.click(screen.getByRole("button", { name: "Delete chat: Earlier question" }));
    expect(m.count("DELETE", /old1$/)).toBe(0);
    expect(screen.getByText("Earlier question")).toBeTruthy();
  });

  it("offers clickable suggestions for an unknown streamer and re-asks with the one picked", async () => {
    const answers = [
      result({ kind: "unknown_streamer", answer: "Hey, I couldn't find a streamer called 'jayz'.", sources: [], streamer: null,
        suggestions: [{ login: "jayden", display_name: "Jayden", avatar_url: "", is_live: true }] }),
      result({ answer: "Found Jayden's clips." }),
    ];
    const { m } = backend([], () => answers.shift()!);
    render(<AskChat />);
    await ask("top clips for jayz");
    await userEvent.click(await screen.findByRole("button", { name: /Jayden/ }));
    expect(await screen.findByText("Found Jayden's clips.")).toBeTruthy();
    const asks = m.calls.filter((c) => /ask$/.test(c.url));
    expect(asks[1].body).toMatchObject({ question: "top clips for jayz", login: "jayden" });
  });

  it("shows web sources as safe links and ignores a source with a dangerous address", async () => {
    backend([], () => result({ sources: [], answer: "7TV is an extension [1].", after: "",
      web_sources: [{ n: 1, title: "7TV", url: "https://7tv.app/", domain: "7tv.app" }, { n: 2, title: "Bad", url: "javascript:alert(1)", domain: "x" }] }));
    render(<AskChat />);
    await ask("what are 7tv emotes");
    const link = await screen.findByRole("link", { name: "7TV" });
    expect(link.getAttribute("href")).toBe("https://7tv.app/");
    expect(screen.getByText("Bad").closest("a")).toBeNull();
  });

  it("shows the server's error instead of hanging, and recovers on the next question", async () => {
    const outcomes = [{ __status: 503, detail: "The server is shutting down" }, result({ answer: "Back again." })];
    mockFetch([
      { url: /\/api\/conversations$/, respond: () => ({ conversations: [] }) },
      { method: "POST", url: /\/api\/ask$/, respond: () => outcomes.shift() },
    ]);
    render(<AskChat />);
    await ask("top clips for jay");
    expect(await screen.findByText("The server is shutting down")).toBeTruthy();
    expect(screen.queryByText("Thinking")).toBeNull();
    await ask("try once more please");
    expect(await screen.findByText("Back again.")).toBeTruthy();
  });

  it("asks before downloading a large batch and does nothing if the user says no", async () => {
    vi.stubGlobal("confirm", vi.fn(() => false));
    const months = [{ month: "2026-01", total_loaded: 16, exact: true, clips: Array.from({ length: 16 }, (_, i) => clip(`m${i}`, 10 + i)) }];
    const { m } = backend([], () => result({ sources: [], months, answer: "Here are the top clips for each month." }));
    render(<AskChat />);
    await ask("top clips each month for jay");
    await userEvent.click(await screen.findByRole("button", { name: "Download all 16 clips" }));
    expect(window.confirm).toHaveBeenCalledOnce();
    expect(m.count("POST", /downloads$/)).toBe(0);
  });

  it("downloads a large batch once the user confirms", async () => {
    const months = [{ month: "2026-01", total_loaded: 16, exact: true, clips: Array.from({ length: 16 }, (_, i) => clip(`m${i}`, 10 + i)) }];
    const { m } = backend([], () => result({ sources: [], months, answer: "Here are the top clips for each month." }));
    render(<AskChat />);
    await ask("top clips each month for jay");
    await userEvent.click(await screen.findByRole("button", { name: "Download all 16 clips" }));
    await waitFor(() => expect(m.count("POST", /downloads$/)).toBe(1));
  });

  it("does not submit a question that is too short", async () => {
    const { m } = backend();
    render(<AskChat />);
    await userEvent.type(screen.getByLabelText(/Ask a question/), "hi");
    expect((screen.getByRole("button", { name: "Ask" }) as HTMLButtonElement).disabled).toBe(true);
    expect(m.count("POST", /ask$/)).toBe(0);
  });
});
