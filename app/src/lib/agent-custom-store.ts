/**
 * Custom Agent Store — user-defined agents persisted in localStorage.
 * Merged with predefined EXPERTS in the AgentsDrawer UI.
 */
import { create } from "zustand";
import { persist } from "zustand/middleware";

export interface CustomAgent {
  id: string;
  name: string;
  enName?: string;
  description: string;
  instructions?: string;
  hue: number;
  icon: string;
  enabled: boolean;
}

interface AgentCustomState {
  agents: CustomAgent[];
  disabledDefaultIds: string[]; // predefined expert IDs that user has disabled

  // Actions
  addAgent: (agent: Omit<CustomAgent, "id">) => string;
  updateAgent: (id: string, patch: Partial<CustomAgent>) => void;
  deleteAgent: (id: string) => void;
  toggleDefaultAgent: (id: string) => void;
}

function genId(): string {
  return `custom-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

export const useAgentCustomStore = create<AgentCustomState>()(
  persist(
    (set) => ({
      agents: [],
      disabledDefaultIds: [],

      addAgent: (agent) => {
        const id = genId();
        set((s) => ({
          agents: [...s.agents, { ...agent, id }],
        }));
        return id;
      },

      updateAgent: (id, patch) => {
        set((s) => ({
          agents: s.agents.map((a) => (a.id === id ? { ...a, ...patch } : a)),
        }));
      },

      deleteAgent: (id) => {
        set((s) => ({
          agents: s.agents.filter((a) => a.id !== id),
        }));
      },

      toggleDefaultAgent: (id) => {
        set((s) => {
          const exists = s.disabledDefaultIds.includes(id);
          return {
            disabledDefaultIds: exists
              ? s.disabledDefaultIds.filter((x) => x !== id)
              : [...s.disabledDefaultIds, id],
          };
        });
      },
    }),
    { name: "normomos-custom-agents" },
  ),
);
