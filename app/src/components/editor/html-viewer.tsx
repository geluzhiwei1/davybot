/**
 * HTMLViewer — Sandboxed HTML content viewer.
 * Renders HTML via iframe srcdoc with security sandboxing.
 */
import { useMemo } from "react";

interface HTMLViewerProps {
  value: string;
  filename?: string;
}

export function HTMLViewer({ value }: HTMLViewerProps) {
  const srcdoc = useMemo(() => {
    // Inject base tag for relative URLs
    if (!value.includes("<base")) {
      return value.replace(/<head([^>]*)>/i, '<head$1><base target="_blank">');
    }
    return value;
  }, [value]);

  return (
    <iframe
      srcDoc={srcdoc}
      sandbox="allow-scripts allow-same-origin allow-popups allow-forms"
      className="w-full h-full border-0 bg-white"
      title="HTML Preview"
    />
  );
}
