import './MetricCard.css';

interface MetricCardProps {
  label: string;
  value: string;
  sentiment?: 'neutral' | 'positive' | 'negative';
}

export function MetricCard({
  label,
  value,
  sentiment = 'neutral',
}: MetricCardProps) {
  const valueClass =
    sentiment === 'positive'
      ? 'metric-card__value metric-card__value--positive'
      : sentiment === 'negative'
        ? 'metric-card__value metric-card__value--negative'
        : 'metric-card__value';

  return (
    <div className="metric-card">
      <span className="metric-card__label">{label}</span>
      <span className={valueClass}>{value}</span>
    </div>
  );
}
