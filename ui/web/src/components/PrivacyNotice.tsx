import { useCore } from '../state/core';

/** One-time privacy notice required before the first cloud call. */
export function PrivacyNotice() {
  const { settings, acknowledgePrivacy } = useCore();

  if (!settings || settings.privacy.notice_acknowledged) {
    return null;
  }

  return (
    <div className="notice">
      <span className="pill pill--warn">privacy</span>
      <p className="notice__text">
        <strong>Free-tier Gemini content may be used by Google to improve its products.</strong>{' '}
        NOVA never uploads your local files or code unless you attach them, and your API key is
        never logged, displayed, or sent anywhere except to the provider.
      </p>
      <button type="button" className="btn btn--primary" onClick={() => void acknowledgePrivacy()}>
        Got it
      </button>
    </div>
  );
}
