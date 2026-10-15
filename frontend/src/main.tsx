import React, { Suspense, lazy } from 'react';
import ReactDOM from 'react-dom/client';
import ValitukiApp from './valituki/ValitukiApp';
import './styles/app.css';

// The earlier OmaGenomi app (DNA analysis, genetic-risk loop, care plans, Apple Health) is kept for restoration but
// hidden from the product. It is loaded only when VITE_ENABLE_LEGACY_APP=true (and the backend has
// LEGACY_FEATURES_ENABLED=1); otherwise neither its code nor its global stylesheet is downloaded.
const legacyEnabled = import.meta.env.VITE_ENABLE_LEGACY_APP === 'true';
const LegacyApp = legacyEnabled
  ? lazy(() => import('./styles/index.css').then(() => import('./App')))
  : null;

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    {LegacyApp ? (
      <Suspense fallback={<p role="status">Loading…</p>}>
        <LegacyApp />
      </Suspense>
    ) : (
      <ValitukiApp />
    )}
  </React.StrictMode>
);
