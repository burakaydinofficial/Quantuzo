import { useState } from 'react';
import type { TrajectoryData } from '../../types/trajectory';
import './TrajectoryViewer.css';

interface TrajectoryViewerProps {
  data: TrajectoryData;
}

export function TrajectoryViewer({ data }: TrajectoryViewerProps) {
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  function toggle(idx: number) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx);
      else next.add(idx);
      return next;
    });
  }

  const messages = data.messages ?? [];
  const info = data.info;

  return (
    <div className="trajectory">
      <div className="trajectory__header">
        Agent Trajectory ({messages.length} messages)
      </div>
      {info && (
        <div className="trajectory__info">
          <span>Exit: {info.exit_status}</span>
          <span>API calls: {info.model_stats?.api_calls ?? '?'}</span>
          <span>Version: {info.mini_version ?? '?'}</span>
        </div>
      )}
      {messages.map((msg, i) => {
        const isExpanded = expanded.has(i);
        const preview = msg.content.slice(0, 120).replace(/\n/g, ' ');
        return (
          <div key={i} className="trajectory__step">
            <div className="trajectory__step-header" onClick={() => toggle(i)}>
              <span className={`trajectory__role trajectory__role--${msg.role}`}>
                {msg.role}
              </span>
              <span className="trajectory__step-preview">{preview}</span>
              <span className="trajectory__toggle">
                {isExpanded ? '\u25B2' : '\u25BC'}
              </span>
            </div>
            {isExpanded && (
              <div className="trajectory__step-content">{msg.content}</div>
            )}
          </div>
        );
      })}
    </div>
  );
}
