import React from 'react';

const RiskBadge = ({ level }) => {
  const normalized = String(level || 'MODERATE').toUpperCase();
  return (
    <span className={`risk-badge risk-${normalized.toLowerCase()}`}>
      <span className="risk-dot" />
      {normalized}
    </span>
  );
};

export default RiskBadge;
