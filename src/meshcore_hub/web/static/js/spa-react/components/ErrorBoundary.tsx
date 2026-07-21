import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    console.error("React ErrorBoundary caught:", error, errorInfo);
  }

  render(): ReactNode {
    if (this.state.hasError) {
      return (
        <div className="flex flex-col items-center justify-center py-20">
          <h1 className="text-4xl font-bold mb-4">
            {window.t("common.error")}
          </h1>
          <p className="text-lg opacity-70 mb-6">
            {window.t("common.failed_to_load_page")}
          </p>
          <p className="text-sm opacity-50 mb-6">
            {this.state.error?.message ?? "Unknown error"}
          </p>
          <a href="/" className="btn btn-primary">
            {window.t("common.go_home")}
          </a>
        </div>
      );
    }
    return this.props.children;
  }
}
