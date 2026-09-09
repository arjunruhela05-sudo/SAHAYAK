import React from 'react';
import { CircleCheck } from 'lucide-react';

const CaseTimeline = ({ events }) => {
  if (!events || events.length === 0) return <div className="empty-inline">No timeline events available.</div>;
  return (
    <div className="timeline">
      {events.map((event, i) => (
        <div className="timeline-item" key={i}>
          <div className="timeline-marker"><CircleCheck size={13} /></div>
          <div className="timeline-content">
            <span>{event.timestamp}</span>
            <strong>{event.event}</strong>
            <p>{event.details}</p>
          </div>
        </div>
      ))}
    </div>
  );
};

export default CaseTimeline;
