import React from 'react';

const SignalCard = ({ signal, level, score }) => {
  const normalized = String(level || 'UNKNOWN').toUpperCase();
  const value = Number(score) || 0;
  return (
    <div className="signal-card">
      <div className="signal-top">
        <span className={`signal-icon signal-${normalized.toLowerCase()}`} />
        <span className="signal-name">{String(signal).replace(/_/g, ' ')}</span>
        <span className={`signal-level signal-${normalized.toLowerCase()}`}>{normalized}</span>
      </div>
      <div className="signal-bottom">
        <div className="mini-track"><div className={`mini-fill signal-${normalized.toLowerCase()}`} style={{ width: `${Math.min(value,100)}%` }} /></div>
        <strong>{value}%</strong>
      </div>
    </div>
  );
};

export default SignalCard;
