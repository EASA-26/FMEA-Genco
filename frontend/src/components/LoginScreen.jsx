import { useState } from 'react';
import { DraftingCompass, Shield } from 'lucide-react';
import AnimatedBackground from './AnimatedBackground.jsx';
import AppIcon from './AppIcon';
import BlueprintDrawing from './BlueprintDrawing.jsx';
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

// The sign-in screen: IZ's Genco Project Theme split on navy, styled as an engineering
// blueprint ("Failure Analysis Report Generator"), the counterpart of FM.ai's
// "spreadsheet terminal" sign-in. Structure from the theme's LoginScreen (gt-login-*,
// styles/genco-theme.css); the blueprint look is styles/login-blueprint.css.
//
// Left (1024px and up): the app badge (icon + description), the app name, the tagline,
// the drawing (BlueprintDrawing, which takes whatever height is left so the page fits
// the window without scrolling) and the three features. Below 1024px the card stands
// alone.
//
// TNB GENCO · TED logo (the theme guide's logo standard, as in FM.ai): from 640px wide,
// top right of the sign-in panel in a 40px row level with the story's app badge, 4vh
// tall (24-36px); on phones, centred under the form at 32px. No "Developed by" label.
//
// It only draws the screen. The app's own sign-in screen keeps its state, validation,
// API call and messages, and passes the form's fields as `children`: this component
// renders them inside the card, under the "Sign in" heading (the page's only h1).
//
// Props: appName (e.g. "FMEA Report": the first word in white, the rest in the accent
// colour), description (worded exactly as in the sidebar), icon (AppIcon key),
// story { tagline, features: [{ icon, label }] } (three features), onSubmit (the form's
// submit handler), footer (optional text under the card).
export default function LoginScreen({ appName, description, icon, story, onSubmit, footer, children }) {
  // Goes up on every submit: the drawing flashes its GENERATE arrow once.
  const [pulseKey, setPulseKey] = useState(0);
  const [nameStem, ...nameRest] = appName.split(' ');

  function handleSubmit(event) {
    setPulseKey((n) => n + 1);
    onSubmit(event);
  }

  return (
    <div className="gt-login">
      <AnimatedBackground variant="login" decorations={false} />

      {/* Story: what the app is for, laid out as a drawing sheet */}
      <section aria-label={`About ${appName}`} className="gt-login-story">
        <div className="gt-login-badge">
          <span className="gt-login-badge-tile">
            <AppIcon app={icon} className="gt-app-icon" />
          </span>
          <span className="gt-login-badge-desc">{description}</span>
        </div>

        {/* The name, not a heading: "Sign in" in the card is the page's h1. */}
        <p className="bp-title">
          {nameStem}
          {nameRest.length > 0 && (
            <>
              {' '}
              <span>{nameRest.join(' ')}</span>
            </>
          )}
        </p>
        <p className="bp-tagline">
          <DraftingCompass aria-hidden="true" />
          {story.tagline}
        </p>

        <BlueprintDrawing pulseKey={pulseKey} />

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
      </section>

      {/* Sign-in */}
      <main className="gt-login-panel">
        {/* Logo, 640px and up: top right of this panel, in a 40px row */}
        <div className="brand-row">
          <Brandmark className="brand-top" />
        </div>

        <div className="gt-login-card-wrap">
          <form className="gt-login-card" onSubmit={handleSubmit} noValidate aria-label={`Sign in to ${appName}`}>
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

          {/* Logo on phones (under 640px): centred under the form, 32px tall */}
          <Brandmark className="brand-phone" />

          {footer && (
            <p className="gt-login-under">
              <Shield size={14} aria-hidden="true" />
              <span>{footer}</span>
            </p>
          )}
        </div>
      </main>
    </div>
  );
}
