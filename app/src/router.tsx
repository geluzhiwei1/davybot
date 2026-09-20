/* eslint-disable react-refresh/only-export-components */
import { createRouter, useRouter } from "@tanstack/react-router";
import { routeTree } from "./routeTree.gen";
import { Loader2 } from "lucide-react";

/**
 * Derive a router basepath from Vite's `base` config.
 * e.g. "/app-ui/" → "/app-ui"
 */
function getBasepathFromBase(base: string): string {
  return base.replace(/\/+$/, "") || "/";
}

/** Get the runtime basepath from Vite's BASE_URL. */
export function getBasepath(): string {
  return getBasepathFromBase(import.meta.env.BASE_URL);
}

function DefaultErrorComponent({ error, reset }: { error: Error; reset: () => void }) {
  const router = useRouter();

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="max-w-md text-center">
        <div className="mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-full bg-destructive/10">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            className="h-8 w-8 text-destructive"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z"
            />
          </svg>
        </div>
        <h1 className="text-2xl font-bold tracking-tight text-foreground">Something went wrong</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          An unexpected error occurred. Please try again.
        </p>
        {import.meta.env.DEV && error && (
          <pre className="mt-4 max-h-60 overflow-auto rounded-md bg-muted p-3 text-left font-mono text-xs text-destructive whitespace-pre-wrap break-all">
            {error.stack || error.message}
          </pre>
        )}
        <div className="mt-6 flex items-center justify-center gap-3">
          <button
            onClick={() => {
              router.invalidate();
              reset();
            }}
            className="inline-flex items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
          >
            Try again
          </button>
          <a
            href={import.meta.env.BASE_URL}
            className="inline-flex items-center justify-center rounded-md border border-input bg-background px-4 py-2 text-sm font-medium text-foreground transition-colors hover:bg-accent"
          >
            Go home
          </a>
        </div>
      </div>
    </div>
  );
}

/** Default Suspense fallback shown while route modules are loading */
function DefaultPendingComponent() {
  return (
    <div className="flex h-full items-center justify-center">
      <div className="flex flex-col items-center gap-3 text-muted-foreground">
        <Loader2 className="h-8 w-8 animate-spin opacity-40" />
        <span className="text-xs">Loading...</span>
      </div>
    </div>
  );
}

// Derive router basepath from Vite's BASE_URL (default: /app-ui)
const basepath = getBasepath();

export const getRouter = () => {
  const router = createRouter({
    routeTree,
    context: {},
    basepath,
    scrollRestoration: true,
    defaultPreloadStaleTime: 0,
    defaultErrorComponent: DefaultErrorComponent,
    defaultPendingComponent: DefaultPendingComponent,
  });

  return router;
};
