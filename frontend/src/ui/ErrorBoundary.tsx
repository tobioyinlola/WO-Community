import { Component, type ErrorInfo, type ReactNode } from "react";
import { Alert, Button } from "../components";

interface Props {
  children: ReactNode;
  /** Changing this (for example the current path) clears an error, so moving on recovers. */
  resetKey?: string;
}

interface State {
  failed: boolean;
}

/** Catches a rendering bug so the member sees a message and a way out, never a blank page. */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { failed: false };

  static getDerivedStateFromError(): State {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // Kept in the console for support; nothing from the page is sent anywhere.
    console.error("A screen failed to render", error, info.componentStack);
  }

  componentDidUpdate(previous: Props): void {
    if (this.state.failed && previous.resetKey !== this.props.resetKey) this.setState({ failed: false });
  }

  render(): ReactNode {
    if (!this.state.failed) return this.props.children;
    return (
      <div style={{ maxWidth: 560, margin: "var(--space-16) auto", padding: "0 var(--space-4)" }}>
        <Alert
          tone="danger"
          title="Something went wrong on this page"
          action={
            <Button size="sm" variant="secondary" onClick={() => window.location.reload()}>
              Reload the page
            </Button>
          }
        >
          It is not your fault, and nothing you entered was lost on the server. Try again, or go back
          to the home page.
        </Alert>
      </div>
    );
  }
}
