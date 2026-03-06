import './ExitStatusBar.css';

interface ExitStatusBarProps {
  exitStatuses: Record<string, number>;
}

const STATUS_COLORS: Record<string, string> = {
  Submitted: '#22c55e',
  LimitsExceeded: '#f59e0b',
};

const ERROR_COLOR = '#ef4444';

function getColor(status: string): string {
  return STATUS_COLORS[status] ?? ERROR_COLOR;
}

export function ExitStatusBar({ exitStatuses }: ExitStatusBarProps) {
  const entries = Object.entries(exitStatuses).sort((a, b) => b[1] - a[1]);
  const total = entries.reduce((sum, [, count]) => sum + count, 0);

  if (total === 0) return null;

  return (
    <div className="exit-status-bar">
      <div className="exit-status-bar__title">Agent Exit Status</div>
      <div className="exit-status-bar__track">
        {entries.map(([status, count]) => (
          <div
            key={status}
            className="exit-status-bar__segment"
            style={{
              flexGrow: count,
              backgroundColor: getColor(status),
            }}
          />
        ))}
      </div>
      <div className="exit-status-bar__legend">
        {entries.map(([status, count]) => (
          <span key={status} className="exit-status-bar__legend-item">
            <span
              className="exit-status-bar__legend-swatch"
              style={{ backgroundColor: getColor(status) }}
            />
            {count} {status}
          </span>
        ))}
      </div>
    </div>
  );
}
