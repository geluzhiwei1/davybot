/**
 * TODO management Zustand store.
 */

import { create } from "zustand";
import type { TodoItem, TodoStatus, TodoGroup, TodoStatistics } from "@/lib/types/todos";

interface TodoState {
  todos: TodoItem[];
  filterStatus: TodoStatus | "all";

  // Actions
  addTodo: (todo: TodoItem) => void;
  updateTodo: (id: string, updates: Partial<TodoItem>) => void;
  removeTodo: (id: string) => void;
  setTodoStatus: (id: string, status: TodoStatus) => void;
  setFilterStatus: (status: TodoStatus | "all") => void;
  getFilteredTodos: () => TodoItem[];
  getStatistics: () => TodoStatistics;
  getGroupedTodos: () => TodoGroup[];
}

export const useTodoStore = create<TodoState>((set, get) => ({
  todos: [],
  filterStatus: "all",

  addTodo: (todo) =>
    set((state) => ({
      todos: [...state.todos, todo],
    })),

  updateTodo: (id, updates) =>
    set((state) => ({
      todos: state.todos.map((todo) => (todo.id === id ? { ...todo, ...updates } : todo)),
    })),

  removeTodo: (id) =>
    set((state) => ({
      todos: state.todos.filter((todo) => todo.id !== id),
    })),

  setTodoStatus: (id, status) =>
    set((state) => ({
      todos: state.todos.map((todo) =>
        todo.id === id
          ? { ...todo, status, completedAt: status === "COMPLETED" ? Date.now() : undefined }
          : todo,
      ),
    })),

  setFilterStatus: (status) => set({ filterStatus: status }),

  getFilteredTodos: () => {
    const state = get();
    if (state.filterStatus === "all") {
      return state.todos;
    }
    return state.todos.filter((todo) => todo.status === state.filterStatus);
  },

  getStatistics: () => {
    const state = get();
    const total = state.todos.length;
    const pending = state.todos.filter((t) => t.status === "PENDING").length;
    const inProgress = state.todos.filter((t) => t.status === "IN_PROGRESS").length;
    const completed = state.todos.filter((t) => t.status === "COMPLETED").length;

    return {
      total,
      pending,
      inProgress,
      completed,
      completionRate: total > 0 ? (completed / total) * 100 : 0,
    };
  },

  getGroupedTodos: () => {
    const state = get();
    const grouped = new Map<string, TodoItem[]>();

    // Group todos by taskNodeId
    for (const todo of state.todos) {
      const key = todo.taskNodeId || "ungrouped";
      if (!grouped.has(key)) {
        grouped.set(key, []);
      }
      grouped.get(key)!.push(todo);
    }

    // Convert to TodoGroup array
    return Array.from(grouped.entries()).map(([taskNodeId, todos]) => ({
      taskNodeId,
      taskNodeName: todos[0]?.taskNodeName || "Ungrouped",
      todos,
    }));
  },
}));
