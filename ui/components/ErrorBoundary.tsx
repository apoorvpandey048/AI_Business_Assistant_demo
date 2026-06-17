"use client";
import React from "react";
import { Button, Card, Icons } from "./ui";

/* Error boundary so a render error in one widget (AnswerPanel, Inspector) never
   blanks the whole page. Shows a friendly fallback with a retry that remounts the
   subtree. React error boundaries must be class components. */
interface Props {
  children: React.ReactNode;
  label?: string;
}
interface State {
  error: Error | null;
}

export default class ErrorBoundary extends React.Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    // eslint-disable-next-line no-console
    console.error(`[ErrorBoundary${this.props.label ? ` ${this.props.label}` : ""}]`, error, info.componentStack);
  }

  reset = () => this.setState({ error: null });

  render() {
    if (this.state.error) {
      return (
        <Card className="flex flex-col items-center gap-2 p-6 text-center">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-danger-soft text-danger">
            <Icons.alert className="h-5 w-5" />
          </div>
          <h3 className="text-[14px] font-semibold text-text-strong">
            Something went wrong displaying {this.props.label || "this section"}.
          </h3>
          <p className="max-w-sm text-[12.5px] text-text-muted">
            The rest of the app is unaffected. You can retry rendering this section.
          </p>
          <Button variant="secondary" size="sm" onClick={this.reset} className="mt-1">
            <Icons.refresh className="h-3.5 w-3.5" />Retry
          </Button>
        </Card>
      );
    }
    return this.props.children;
  }
}
