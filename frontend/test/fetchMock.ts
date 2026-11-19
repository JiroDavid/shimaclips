import { vi } from "vitest";

export type Route = {
  method?: string;
  url: RegExp;
  respond: (call: { url: string; body: unknown }) => unknown;
  status?: number;
};

export type Call = { url: string; method: string; body: unknown };

export function mockFetch(routes: Route[]) {
  const calls: Call[] = [];
  const fn = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = init?.method ?? "GET";
    const body = init?.body ? JSON.parse(String(init.body)) : undefined;
    calls.push({ url, method, body });
    const route = routes.find((r) => (r.method ?? "GET") === method && r.url.test(url));
    if (!route) return new Response(JSON.stringify({ detail: `no mock for ${method} ${url}` }), { status: 500 });
    const out = route.respond({ url, body }) as { __status?: number } | undefined;
    const status = out && typeof out === "object" && "__status" in out ? out.__status : undefined;
    return new Response(JSON.stringify(out), {
      status: status ?? route.status ?? 200,
      headers: { "content-type": "application/json" },
    });
  });
  vi.stubGlobal("fetch", fn);
  return { calls, fn, count: (method: string, re: RegExp) => calls.filter((c) => c.method === method && re.test(c.url)).length };
}
