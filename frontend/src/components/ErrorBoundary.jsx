import { Component } from 'react';
import { RefreshCw, TriangleAlert } from 'lucide-react';

// Last line of defence: if a screen fails to draw (for example an unexpected value
// in the report), show a plain message with a way out instead of a blank page.
// Technical details go to the browser console only, never to the screen.
//
// variant "section": used around the content area, so the sidebar and top bar keep
// working; it resets itself when `resetKey` changes (another section, UOIR or tab).
// variant "page": the outermost fallback, offering a reload.
// `onError` (optional) runs once when the boundary catches an error; the page variant
// uses it to discard the workbook on the server, because the screen that held it (and
// its leave-the-page handlers) is gone.
export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { failed: false };
  }

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error, info) {
    console.error('FMEA Report: a screen failed to draw.', error, info && info.componentStack);
    if (this.props.onError) {
      try {
        this.props.onError(error);
      } catch {
        // The fallback screen is shown whatever happens here.
      }
    }
  }

  componentDidUpdate(previousProps) {
    if (this.state.failed && previousProps.resetKey !== this.props.resetKey) {
      this.setState({ failed: false });
    }
  }

  render() {
    if (!this.state.failed) return this.props.children;

    if (this.props.variant === 'section') {
      return (
        <div className="view-narrow">
          <div className="alert alert-warning" role="alert">
            <TriangleAlert className="alert-icon" size={20} aria-hidden="true" />
            <div className="alert-body">
              <div className="alert-title">
                <span className="alert-label">Not shown</span>
                <span>This part of the report could not be shown</span>
              </div>
              <div className="alert-text">
                Something in the workbook data could not be displayed here. Choose another section, UOIR or tab from the
                menu, or upload the workbook again. If it keeps happening, contact support.
              </div>
            </div>
          </div>
        </div>
      );
    }

    return (
      <div className="splash">
        <div className="splash-card" role="alert">
          <span className="icon-tile icon-tile-muted" aria-hidden="true">
            <TriangleAlert size={22} />
          </span>
          <h1>This page could not be shown</h1>
          <p>
            Something in the workbook data could not be displayed. Reload the page and try again. If it keeps happening, upload
            the workbook again or contact support.
          </p>
          <button type="button" className="btn btn-primary" onClick={() => window.location.reload()}>
            <RefreshCw size={16} aria-hidden="true" /> Reload the page
          </button>
        </div>
      </div>
    );
  }
}
