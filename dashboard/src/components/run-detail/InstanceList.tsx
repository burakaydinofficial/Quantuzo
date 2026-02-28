import { useState } from 'react';
import { Link } from 'react-router-dom';
import type { EvaluationInstances } from '../../types/evaluation';
import './InstanceList.css';

type Tab = 'resolved' | 'unresolved' | 'incomplete';

interface InstanceListProps {
  instances: EvaluationInstances;
  runId: string;
}

export function InstanceList({ instances, runId }: InstanceListProps) {
  const [tab, setTab] = useState<Tab>('resolved');

  const tabData: Record<Tab, { ids: string[]; badge: string }> = {
    resolved: { ids: instances.resolved_ids ?? [], badge: 'resolved' },
    unresolved: { ids: instances.unresolved_ids ?? [], badge: 'unresolved' },
    incomplete: { ids: instances.incomplete_ids ?? [], badge: 'incomplete' },
  };

  const current = tabData[tab];

  return (
    <div>
      <div className="instance-list__tabs">
        {(['resolved', 'unresolved', 'incomplete'] as Tab[]).map((t) => (
          <button
            key={t}
            className={
              tab === t
                ? 'instance-list__tab instance-list__tab--active'
                : 'instance-list__tab'
            }
            onClick={() => setTab(t)}
          >
            {t.charAt(0).toUpperCase() + t.slice(1)} ({tabData[t].ids.length})
          </button>
        ))}
      </div>
      <div className="instance-list__items">
        {current.ids.length === 0 ? (
          <div className="instance-list__empty">No instances</div>
        ) : (
          current.ids.map((id) => (
            <Link
              key={id}
              to={`/run/${encodeURIComponent(runId)}/instance/${encodeURIComponent(id)}`}
              className="instance-list__item"
            >
              <span className={`instance-list__badge instance-list__badge--${current.badge}`} />
              {id}
            </Link>
          ))
        )}
      </div>
    </div>
  );
}
