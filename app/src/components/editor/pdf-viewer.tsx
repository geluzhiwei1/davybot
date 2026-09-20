/**
 * PDFViewer — Browser-native PDF viewer via iframe.
 * Supports URL-based and base64 PDF content.
 */
import { useTranslation } from "react-i18next";

interface PDFViewerProps {
  url?: string;
  base64?: string;
  filename?: string;
}

export function PDFViewer({ url, base64 }: PDFViewerProps) {
  const { t } = useTranslation("editorUi");
  const pdfUrl = base64 ? `data:application/pdf;base64,${base64}` : (url ?? "");

  if (!pdfUrl) {
    return (
      <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
        {t("pdf.noContent")}
      </div>
    );
  }

  return <iframe src={pdfUrl} className="w-full h-full border-0" title="PDF Viewer" />;
}
