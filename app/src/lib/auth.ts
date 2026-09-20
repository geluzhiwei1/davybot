/**
 * Auth service — thin facade over the Zustand auth store.
 * Legacy code imported from this module; it now re-exports
 * types and helpers from auth-store.ts for backward compat.
 */

export { useAuthStore, type AuthUser } from "./auth-store";
