/**
 * DrawioEditor — Embed draw.io diagram editor via iframe.
 * Uses the embed mode with postMessage communication.
 */
import { useEffect, useRef, useCallback } from "react";

interface DrawioEditorProps {
  value: string;
  onChange?: (value: string) => void;
  readOnly?: boolean;
}

const DRAWIO_URL = "https://embed.diagrams.net/";

export function DrawioEditor({ value, onChange, readOnly = false }: DrawioEditorProps) {
  const iframeRef = useRef<HTMLIFrameElement>(null);

  const handleMessage = useCallback(
    (event: MessageEvent) => {
      if (event.origin !== "https://embed.diagrams.net") return;
      const { type, xml } = event.data;
      if (type === "save" && xml && onChange) {
        onChange(xml);
      }
    },
    [onChange],
  );

  useEffect(() => {
    window.addEventListener("message", handleMessage);
    return () => window.removeEventListener("message", handleMessage);
  }, [handleMessage]);

  const iframeSrc = `${DRAWIO_URL}?embed=1&proto=json&spin=1&saveAndExit=1&noSaveBtn=${readOnly ? 1 : 0}&noExitBtn=0`;

  return (
    <div className="w-full h-full relative">
      <iframe
        ref={iframeRef}
        src={iframeSrc}
        className="w-full h-full border-0"
        title="Draw.io Editor"
        onLoad={() => {
          // Send initial XML to draw.io
          if (iframeRef.current?.contentWindow && value) {
            iframeRef.current.contentWindow.postMessage(
              { action: "load", autosave: 0, xml: value },
              "*",
            );
          }
        }}
      />
    </div>
  );
}
