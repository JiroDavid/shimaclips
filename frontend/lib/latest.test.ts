import { describe, expect, it } from "vitest";
import { createLatest } from "./latest";

function deferred<T>() {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

describe("createLatest", () => {
  it("superseded run returns ok:false even if it resolves last", async () => {
    const latest = createLatest();
    const first = deferred<string>();
    const second = deferred<string>();
    const r1 = latest.run(() => first.promise);
    const r2 = latest.run(() => second.promise);
    second.resolve("two");
    first.resolve("one");
    expect(await r2).toEqual({ ok: true, value: "two" });
    expect(await r1).toEqual({ ok: false });
  });

  it("previous signal is aborted when a new run starts", async () => {
    const latest = createLatest();
    let firstSignal!: AbortSignal;
    const r1 = latest.run(async (s) => {
      firstSignal = s;
      return 1;
    });
    expect(firstSignal.aborted).toBe(false);
    const r2 = latest.run(async () => 2);
    expect(firstSignal.aborted).toBe(true);
    await Promise.all([r1, r2]);
  });

  it("rapid 5 runs only the last is ok", async () => {
    const latest = createLatest();
    const results = await Promise.all(
      [1, 2, 3, 4, 5].map((n) => latest.run(async () => n)),
    );
    expect(results.map((r) => r.ok)).toEqual([false, false, false, false, true]);
  });

  it("abort errors resolve ok:false", async () => {
    const latest = createLatest();
    const r = await latest.run(async () => {
      throw new DOMException("aborted", "AbortError");
    });
    expect(r).toEqual({ ok: false });
  });

  it("errors from the latest run reject", async () => {
    const latest = createLatest();
    await expect(latest.run(async () => { throw new Error("boom"); })).rejects.toThrow("boom");
  });

  it("errors from a superseded run resolve ok:false", async () => {
    const latest = createLatest();
    const first = deferred<string>();
    const r1 = latest.run(() => first.promise);
    const r2 = latest.run(async () => "x");
    first.reject(new Error("late"));
    expect(await r1).toEqual({ ok: false });
    expect(await r2).toEqual({ ok: true, value: "x" });
  });
});
