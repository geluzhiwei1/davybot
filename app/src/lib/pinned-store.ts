/**
 * Pinned menu store — tracks sidebar menu items the user has "pinned".
 * Pinned items are mirrored onto the home page for quick access.
 * Persisted to localStorage so pins survive refresh.
 */
import { create } from "zustand";
import { persist } from "zustand/middleware";

export interface PinnedItem {
  /** Unique key: the route path, e.g. "/normflow/contracts" */
  key: string;
  /** Display title */
  title: string;
  /** Route to navigate to */
  route: string;
  /** Icon name (kebab-case string matching lucide icon naming) */
  icon: string;
}

interface PinnedState {
  pinned: PinnedItem[];
  togglePin: (item: PinnedItem) => void;
  unpin: (key: string) => void;
  isPinned: (key: string) => boolean;
}

export const usePinnedStore = create<PinnedState>()(
  persist(
    (set, get) => ({
      pinned: [],

      togglePin: (item) => {
        const { pinned } = get();
        const exists = pinned.some((p) => p.key === item.key);
        if (exists) {
          set({ pinned: pinned.filter((p) => p.key !== item.key) });
        } else {
          set({ pinned: [...pinned, item] });
        }
      },

      unpin: (key) => set((s) => ({ pinned: s.pinned.filter((p) => p.key !== key) })),

      isPinned: (key) => get().pinned.some((p) => p.key === key),
    }),
    {
      name: "normnomos-pinned-v1",
      partialize: (s) => ({ pinned: s.pinned }),
    },
  ),
);
