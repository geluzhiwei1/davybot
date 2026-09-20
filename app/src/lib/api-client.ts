/**
 * **Primary HTTP API client** — thin re-export shim.
 *
 * All implementation has been moved to src/lib/api/ domain modules.
 * This file re-exports everything so existing consumers continue to work
 * without any import changes.
 *
 * @module api-client
 */
export * from "./api/index";
