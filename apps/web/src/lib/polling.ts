/** Sequential polling: no overlapping requests; hidden tabs do not poll. */
export function pollWhileVisible(check: () => Promise<boolean>, failed: (error: unknown) => void, interval = 3000): () => void {
  let active = true;
  let timer: ReturnType<typeof setTimeout>;
  async function tick() {
    if (!active) return;
    try {
      if (typeof document === "undefined" || document.visibilityState !== "hidden") {
        if (!await check()) return;
      }
      if (active) timer = setTimeout(() => void tick(), interval);
    } catch (error) {if (active) failed(error);}
  }
  timer = setTimeout(() => void tick(), interval);
  return () => {active = false; clearTimeout(timer);};
}
