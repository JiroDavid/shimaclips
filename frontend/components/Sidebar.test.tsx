// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import Sidebar from "@/components/Sidebar";
import { mockFetch } from "@/test/fetchMock";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

const chats = [
  { id: "a", title: "Top 10 clips for arky", updated_at: "2026-11-19T10:00:00Z" },
  { id: "b", title: "What are 7TV emotes?", updated_at: "2026-11-18T10:00:00Z" },
];

function setup(over: Partial<React.ComponentProps<typeof Sidebar>> = {}) {
  mockFetch([{ url: /\/search/, respond: () => ({ results: [] }) }]);
  const props = { open: true, onToggle: vi.fn(), conversations: chats, activeId: null as string | null, error: null as string | null, onNew: vi.fn(), onOpen: vi.fn(), onDelete: vi.fn(), ...over };
  render(<Sidebar {...props} />);
  return props;
}

describe("Sidebar", () => {
  it("lists past chats and marks the open one", () => {
    setup({ activeId: "b" });
    expect(screen.getByText("Top 10 clips for arky")).toBeTruthy();
    expect(screen.getByText("What are 7TV emotes?").getAttribute("aria-current")).toBe("page");
    expect(screen.getByText("Top 10 clips for arky").getAttribute("aria-current")).toBeNull();
  });

  it("opens a chat when it is clicked", async () => {
    const p = setup();
    await userEvent.click(screen.getByText("What are 7TV emotes?"));
    expect(p.onOpen).toHaveBeenCalledWith("b");
  });

  it("deletes a chat from its own button without opening it", async () => {
    const p = setup();
    await userEvent.click(screen.getByRole("button", { name: "Delete chat: Top 10 clips for arky" }));
    expect(p.onDelete).toHaveBeenCalledWith("a");
    expect(p.onOpen).not.toHaveBeenCalled();
  });

  it("starts a new chat from the logo and from the New chat button", async () => {
    const p = setup();
    await userEvent.click(screen.getByRole("button", { name: "Shimaclips, start a new chat" }));
    await userEvent.click(screen.getByRole("button", { name: "New chat" }));
    expect(p.onNew).toHaveBeenCalledTimes(2);
  });

  it("opens the manual streamer search and goes to that streamer's calendar", async () => {
    setup();
    const toggle = screen.getByRole("button", { name: "Manual Streamer Search" });
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    await userEvent.click(toggle);
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    const box = screen.getByRole("combobox");
    await userEvent.type(box, "yugi2x{Enter}");
    expect(push).toHaveBeenCalledWith("/browse?streamer=yugi2x");
  });

  it("explains an empty history and shows history errors", () => {
    setup({ conversations: [] });
    expect(screen.getByText("Your chats will appear here.")).toBeTruthy();
  });

  it("shows a history error instead of the empty message", () => {
    setup({ conversations: [], error: "History is unavailable right now." });
    expect(screen.getByText("History is unavailable right now.")).toBeTruthy();
    expect(screen.queryByText("Your chats will appear here.")).toBeNull();
  });

  it("collapses to a narrow rail that can be expanded again", async () => {
    const p = setup({ open: false });
    expect(screen.queryByText("Recents")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Open sidebar" }));
    expect(p.onToggle).toHaveBeenCalledOnce();
  });
});
