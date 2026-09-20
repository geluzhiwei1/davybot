/**
 * Model store — LLM model list fetched from backend.
 * Extracted from store.ts for domain separation.
 */
import { toastError } from "../api/client.js";
import { create } from "zustand";
import { llmApi } from "../api-client";

// ── Types (re-exported from store.ts) ──────────────────────────────

export interface LLMModel {
  id: string;
  name: string;
  displayName?: string;
  provider?: string;
}

// ── Store ───────────────────────────────────────────────────────────

interface ModelState {
  models: LLMModel[];
  fetchModels: () => Promise<void>;
}

export const useModelStore = create<ModelState>()((set) => ({
  models: [],

  fetchModels: async () => {
    try {
      const data = await llmApi.listGlobalModels();
      if (data.availableLLMs) {
        const models: LLMModel[] = data.availableLLMs.map(
          (m: { id: string; name: string; displayName?: string; provider?: string }) => ({
            id: m.id,
            name: m.displayName || m.name,
            displayName: m.displayName,
            provider: m.provider,
          }),
        );
        set({ models });
      }
    } catch (e) {
      console.error("[ModelStore] fetchModels failed:", e);
      toastError("加载模型列表失败", e);
    }
  },
}));
