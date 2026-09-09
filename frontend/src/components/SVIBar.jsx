import React from 'react';

const SVIBar = ({ score = 0, label = 'Social Vulnerability Index' }) => {
  const value = Math.max(0, Math.min(100, Number(score) || 0));
  const level = value >= 75 ? 'critical' : value >= 50 ? 'high' : value >= 25 ? 'moderate' : 'low';
  return (
    <div className="svi-widget">
      <div className="svi-head">
        <div><span className="eyebrow">Index score</span><strong>{label}</strong></div>
        <div className={`svi-number ${level}`}>{value}<small>/100</small></div>
      </div>
      <div className="svi-track"><div className={`svi-fill ${level}`} style={{ width: `${value}%` }} /></div>
      <div className="svi-scale"><span>Low</span><span>Moderate</span><span>High</span><span>Critical</span></div>
    </div>
  );
};

export default SVIBar;
