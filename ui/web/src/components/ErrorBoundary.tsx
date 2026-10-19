import { Component } from 'react';
import type { ErrorInfo, ReactNode } from 'react';

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

/** Keeps a render-time failure in one panel from blanking the whole window. */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error('NOVA UI error:', error, info.componentStack);
  }

  private retry = (): void => {
    this.setState({ error: null });
  };

  render(): ReactNode {
    const { error } = this.state;
    if (!error) {
      return this.props.children;
    }
    return (
      <div className="crash">
        <div className="crash__card glass">
          <span className="pill pill--bad">interface error</span>
          <h1 className="crash__title">NOVA hit a snag</h1>
          <p className="crash__text">
            Part of the interface failed to render. Nothing was sent anywhere. Try
            again, or reload the view.
          </p>
          <pre className="crash__detail mono">{error.message}</pre>
          <div className="crash__actions">
            <button type="button" className="btn btn--primary" onClick={this.retry}>
              Try again
            </button>
            <button
              type="button"
              className="btn btn--ghost"
              onClick={() => window.location.reload()}
            >
              Reload
            </button>
          </div>
        </div>
      </div>
    );
  }
}
