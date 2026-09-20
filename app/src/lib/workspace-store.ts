/**
 * Workspace store — migrated from legalbot/webui/src/stores/workspace.ts
 * Zustand store for workspace and conversation management.
 */
import { create } from "zustand";

interface Workspace {
  id: string;
  name: string;
  path?: string;
  createdAt?: string;
  updatedAt?: string;
}

interface Conversation {
  id: string;
  title: string;
  createdAt?: string;
  updatedAt?: string;
  lastUpdated?: string;
  messageCount?: number;
}

interface MessagePagination {
  hasMore: boolean;
  total: number;
  loaded: number;
}

interface WorkspaceStoreState {
  currentWorkspaceId: string | null;
  currentConversationId: string | null;
  workspaceList: Workspace[];
  conversationList: Conversation[];
  messagePagination: MessagePagination;
  isLoadingMore: boolean;

  // Actions
  setWorkspace: (workspaceId: string) => void;
  setConversation: (conversationId: string) => void;
  setWorkspaceList: (workspaces: Workspace[]) => void;
  setConversationList: (conversations: Conversation[]) => void;
  addWorkspace: (workspace: Workspace) => void;
  addConversation: (conversation: Conversation) => void;
  clearCurrentConversation: () => void;
  setMessagePagination: (pagination: Partial<MessagePagination>) => void;
  setIsLoadingMore: (loading: boolean) => void;
  generateConversationTitle: (userMessage: string) => string;
}

export const useWorkspaceStore = create<WorkspaceStoreState>((set) => ({
  currentWorkspaceId: null,
  currentConversationId: null,
  workspaceList: [],
  conversationList: [],
  messagePagination: { hasMore: false, total: 0, loaded: 0 },
  isLoadingMore: false,

  setWorkspace: (workspaceId) => {
    // Persist to localStorage for services that read it (e.g. checklist-service)
    if (typeof window !== "undefined") {
      localStorage.setItem("normnomos-workspace-id", workspaceId);
    }
    set({ currentWorkspaceId: workspaceId });
  },

  setConversation: (conversationId) => set({ currentConversationId: conversationId }),

  setWorkspaceList: (workspaces) => set({ workspaceList: workspaces }),

  setConversationList: (conversations) => {
    set((s) => {
      // Auto-select latest conversation if none selected
      if (conversations.length > 0 && !s.currentConversationId) {
        const sorted = [...conversations].sort((a, b) => {
          const dateA = new Date(a.updatedAt || a.createdAt || 0).getTime();
          const dateB = new Date(b.updatedAt || b.createdAt || 0).getTime();
          return dateB - dateA;
        });
        return {
          conversationList: conversations,
          currentConversationId: sorted[0].id,
        };
      }
      return { conversationList: conversations };
    });
  },

  addWorkspace: (workspace) => {
    // Persist to localStorage for services that read it (e.g. checklist-service)
    if (typeof window !== "undefined") {
      localStorage.setItem("normnomos-workspace-id", workspace.id);
    }
    set((s) => ({
      workspaceList: [...s.workspaceList, workspace],
      currentWorkspaceId: workspace.id,
    }));
  },

  addConversation: (conversation) => {
    set((s) => ({
      conversationList: [...s.conversationList, conversation],
      currentConversationId: conversation.id,
    }));
  },

  clearCurrentConversation: () => set({ currentConversationId: null }),

  setMessagePagination: (pagination) => {
    set((s) => ({
      messagePagination: { ...s.messagePagination, ...pagination },
    }));
  },

  setIsLoadingMore: (loading) => set({ isLoadingMore: loading }),

  generateConversationTitle: (userMessage: string) => {
    const trimmed = userMessage.trim();
    if (trimmed.length <= 20) return trimmed;
    const title = trimmed.substring(0, 30);
    const sentenceEnd = title.search(/[。！？.!?\n]/);
    if (sentenceEnd !== -1 && sentenceEnd > 5) return title.substring(0, sentenceEnd);
    return title + "...";
  },
}));
