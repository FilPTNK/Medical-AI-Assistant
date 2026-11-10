import React from 'react';

// Display the supplied transparent PNG at its visible bounds; keep the source intact.
export default function FilLogo({ className = 'fil-logo' }) {
  return (
    <svg className={className} viewBox="525 130 1130 490" role="img" aria-label="Fil">
      <image href="/fil-logo.png" width="2172" height="724" />
    </svg>
  );
}
