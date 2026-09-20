import { Component, type ErrorInfo, type ReactNode } from "react";
import i18n from "@/lib/i18n";
import { AlertTriangle, RefreshCw, Bug } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
  onError?: (error: Error, errorInfo: ErrorInfo) => void;
}

interface State {
  hasError: boolean;
  error: Error | null;
  errorInfo: ErrorInfo | null;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null, errorInfo: null };
  }

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    this.setState({ errorInfo });
    this.props.onError?.(error, errorInfo);
    console.error("[ErrorBoundary]", error, errorInfo);
  }

  handleReset = (): void => {
    this.setState({ hasError: false, error: null, errorInfo: null });
  };

  render(): ReactNode {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <div className="flex min-h-[200px] items-center justify-center p-4">
          <Card className="w-full max-w-lg border-destructive/30">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-destructive">
                <AlertTriangle className="h-5 w-5" />
                {i18n.t("errorBoundary.title", { ns: "commonUi" })}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <p className="text-sm text-muted-foreground">
                {i18n.t("errorBoundary.desc", { ns: "commonUi" })}
              </p>
              {this.state.error && (
                <pre className="max-h-32 overflow-auto rounded bg-muted p-3 text-xs text-muted-foreground">
                  {this.state.error.message}
                </pre>
              )}
              {this.state.errorInfo && (
                <details className="text-xs text-muted-foreground">
                  <summary className="cursor-pointer hover:text-foreground">
                    {i18n.t("errorBoundary.componentStack", { ns: "commonUi" })}
                  </summary>
                  <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap">
                    {this.state.errorInfo.componentStack}
                  </pre>
                </details>
              )}
              <div className="flex gap-2">
                <Button onClick={this.handleReset} size="sm" variant="outline">
                  <RefreshCw className="mr-2 h-4 w-4" />
                  {i18n.t("errorBoundary.reset", { ns: "commonUi" })}
                </Button>
                <Button
                  onClick={() => {
                    const body = [
                      `Error: ${this.state.error?.message}`,
                      `Stack: ${this.state.error?.stack}`,
                      `Component: ${this.state.errorInfo?.componentStack}`,
                    ].join("\n\n");
                    console.error(body);
                  }}
                  size="sm"
                  variant="ghost"
                >
                  <Bug className="mr-2 h-4 w-4" />
                  {i18n.t("errorBoundary.report", { ns: "commonUi" })}
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      );
    }

    return this.props.children;
  }
}
