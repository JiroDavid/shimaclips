import { describe, expect, it } from "vitest";
import { mockFetch } from "@/test/fetchMock";
import { askQuestion, deleteConversation, getConversation, listConversations, startTranscription } from "@/lib/api";

describe("ask api client", () => {
  it("sends the question, the remembered streamer and the conversation id", async () => {
    const m = mockFetch([{ method: "POST", url: /\/api\/ask$/, respond: () => ({ answer: "ok" }) }]);
    await askQuestion("how many clips", "jay", "abc");
    expect(m.calls[0].body).toEqual({ question: "how many clips", login: "jay", conversation_id: "abc" });
  });

  it("turns a server error message into an Error the UI can show", async () => {
    mockFetch([{ method: "POST", url: /\/api\/ask$/, status: 422, respond: () => ({ detail: "invalid streamer login" }) }]);
    await expect(askQuestion("how many clips", "../x", null)).rejects.toThrow("invalid streamer login");
  });

  it("joins validation messages when the server returns a list", async () => {
    mockFetch([{ method: "POST", url: /\/api\/ask$/, status: 422, respond: () => ({ detail: [{ msg: "Value error, too short" }, { msg: "bad" }] }) }]);
    await expect(askQuestion("hi", null, null)).rejects.toThrow("too short; bad");
  });

  it("falls back to a status message when the server sends no detail", async () => {
    mockFetch([{ method: "POST", url: /\/api\/ask$/, status: 503, respond: () => ({}) }]);
    await expect(askQuestion("how many clips", null, null)).rejects.toThrow("Request failed (503)");
  });

  it("lists, opens and deletes conversations with the right verbs and encoded ids", async () => {
    const m = mockFetch([
      { url: /\/api\/conversations$/, respond: () => ({ conversations: [{ id: "a", title: "t", updated_at: "x" }] }) },
      { url: /\/api\/conversations\/a%2Fb$/, respond: () => ({ id: "a/b", title: "t", turns: [] }) },
      { method: "DELETE", url: /\/api\/conversations\/a%2Fb$/, respond: () => ({ ok: true }) },
    ]);
    expect(await listConversations()).toHaveLength(1);
    expect((await getConversation("a/b")).id).toBe("a/b");
    await deleteConversation("a/b");
    expect(m.calls.map((c) => c.method)).toEqual(["GET", "GET", "DELETE"]);
  });

  it("starts transcription with a POST", async () => {
    const m = mockFetch([{ method: "POST", url: /\/api\/streamers\/newbie\/transcribe$/, respond: () => ({ state: "queued" }) }]);
    expect((await startTranscription("newbie")).state).toBe("queued");
    expect(m.calls[0].method).toBe("POST");
  });
});
