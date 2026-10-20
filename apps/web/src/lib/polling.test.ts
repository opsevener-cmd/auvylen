import {afterEach, describe, expect, it, vi} from "vitest";
import {pollWhileVisible} from "./polling";
afterEach(() => {vi.useRealTimers(); vi.unstubAllGlobals();});
describe("bounded job polling", () => {
  it("does not overlap slow requests and stops after completion", async () => {
    vi.useFakeTimers();
    let resolve!: (value: boolean) => void;
    const check = vi.fn(() => new Promise<boolean>(done => {resolve = done;}));
    const stop = pollWhileVisible(check, vi.fn());
    await vi.advanceTimersByTimeAsync(15000);
    expect(check).toHaveBeenCalledTimes(1);
    resolve(false); await vi.advanceTimersByTimeAsync(15000);
    expect(check).toHaveBeenCalledTimes(1); stop();
  });
  it("pauses hidden tabs, resumes visibility, and cancels cleanly", async () => {
    vi.useFakeTimers();
    const document = {visibilityState: "hidden"}; vi.stubGlobal("document", document);
    const check = vi.fn(async () => true);
    const stop = pollWhileVisible(check, vi.fn());
    await vi.advanceTimersByTimeAsync(12000); expect(check).not.toHaveBeenCalled();
    document.visibilityState = "visible";
    await vi.advanceTimersByTimeAsync(3000); expect(check).toHaveBeenCalledTimes(1);
    stop(); await vi.advanceTimersByTimeAsync(12000); expect(check).toHaveBeenCalledTimes(1);
  });
});
