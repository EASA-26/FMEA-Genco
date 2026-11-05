import AnimatedBackground from './AnimatedBackground.jsx';
import AppIcon from './AppIcon';
import brandmark1x from '../assets/tnb-genco-ted-white@1x.png';
import brandmark2x from '../assets/tnb-genco-ted-white@2x.png';
import brandmark3x from '../assets/tnb-genco-ted-white@3x.png';

const Brandmark = ({ className }) => (
  <img
    src={brandmark1x}
    srcSet={`${brandmark1x} 1x, ${brandmark2x} 2x, ${brandmark3x} 3x`}
    alt="TNB GENCO · TED"
    className={className}
  />
);

// IZ's Genco Project Theme login: the split on navy (plain-CSS port of the kit's
// LoginScreen.tsx; styles are the gt-login-* classes in styles/genco-theme.css).
// What the app is for on the left, the sign-in card on the right; below 1024px the
// story is hidden and the card stands alone with the brandmark above it. Always light.
//
// It only draws the screen. The app's own sign-in screen keeps its state, validation,
// API call and messages, and passes the form's fields as `children`: this component
// renders them inside the card, under the "Sign in" heading (the page's only h1).
//
// Props: appName, description (worded exactly as in the sidebar), icon (AppIcon key),
// story { headline, accent, summary, features: [{ icon, label }] } (three features),
// onSubmit (the form's submit handler), footer (optional text under the card).
export default function LoginScreen({ appName, description, icon, story, onSubmit, footer, children }) {
  return (
    <div className="gt-login">
      <AnimatedBackground variant="login" />

      {/* Story: what the app is for */}
      <section aria-label={`About ${appName}`} className="gt-login-story">
        <div className="gt-login-badge">
          <span className="gt-login-badge-tile">
            <AppIcon app={icon} className="gt-app-icon" />
          </span>
          <span>
            <span className="gt-login-badge-name">{appName}</span>
            <span className="gt-login-badge-desc">{description}</span>
          </span>
        </div>

        <div className="gt-login-story-body">
          {/* A tagline, not a heading: "Sign in" in the card is the page's h1. */}
          <p className="gt-login-headline">
            {story.headline}
            <br />
            <span className="gt-login-accent">{story.accent}</span>
          </p>
          <p className="gt-login-summary">{story.summary}</p>
          <ul role="list" className="gt-login-features">
            {story.features.map(({ icon: FeatureIcon, label }) => (
              <li key={label} className="gt-login-feature">
                <span className="gt-login-feature-icon">
                  <FeatureIcon size={16} aria-hidden="true" />
                </span>
                {label}
              </li>
            ))}
          </ul>
        </div>

        <div>
          <p className="gt-login-dev-label">Developed by</p>
          <Brandmark className="gt-login-brandmark" />
        </div>
      </section>

      {/* Sign-in */}
      <main className="gt-login-panel">
        <div className="gt-login-card-wrap">
          <Brandmark className="gt-login-brandmark-top" />

          <form className="gt-login-card" onSubmit={onSubmit} noValidate aria-label={`Sign in to ${appName}`}>
            <div className="gt-login-card-head">
              <span className="gt-icon-tile">
                <AppIcon app={icon} className="gt-app-icon" />
              </span>
              <div>
                <p className="gt-login-card-name">{appName}</p>
                <p className="gt-login-card-desc">{description}</p>
              </div>
            </div>

            <h1 className="gt-login-title">Sign in</h1>

            {children}
          </form>

          {footer && <p className="gt-login-under">{footer}</p>}
        </div>
      </main>
    </div>
  );
}
