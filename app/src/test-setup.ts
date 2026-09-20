import "@testing-library/jest-dom/vitest";

// Node >= 25 ships a global localStorage backed by --localstorage-file; without a
// valid path vitest's jsdom env inherits a crippled Storage (no .clear). Provide a
// deterministic in-memory stub when the global one is unusable.
const ls = globalThis.localStorage as Storage | undefined;
if (typeof ls?.clear !== "function") {
  const store = new Map<string, string>();
  const stub: Storage = {
    getItem: (k) => store.get(String(k)) ?? null,
    setItem: (k, v) => void store.set(String(k), String(v)),
    removeItem: (k) => void store.delete(String(k)),
    clear: () => store.clear(),
    key: (i) => [...store.keys()][Number(i)] ?? null,
    get length() {
      return store.size;
    },
  };
  Object.defineProperty(globalThis, "localStorage", {
    value: stub,
    configurable: true,
    writable: true,
  });
}
