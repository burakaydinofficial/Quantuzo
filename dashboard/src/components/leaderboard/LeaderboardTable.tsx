import { useState, useMemo, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import type { LeaderboardRow } from '../../types/leaderboard';
import { kvLabel } from '../../utils/kv-config';
import { deltaBaseline } from '../../utils/metrics';
import { fmtPct, fmtDelta } from '../../utils/format';
import './LeaderboardTable.css';

type SortKey = 'model_name' | 'kv' | 'agent_version' | 'resolved' | 'total' | 'rate' | 'delta';
type SortDir = 'asc' | 'desc';

interface LeaderboardTableProps {
  rows: LeaderboardRow[];
  allRows: LeaderboardRow[];
}

export function LeaderboardTable({ rows, allRows }: LeaderboardTableProps) {
  const navigate = useNavigate();
  const [sortKey, setSortKey] = useState<SortKey>('rate');
  const [sortDir, setSortDir] = useState<SortDir>('desc');

  function handleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortDir('desc');
    }
  }

  const sorted = useMemo(() => {
    const copy = [...rows];
    const dir = sortDir === 'asc' ? 1 : -1;
    copy.sort((a, b) => {
      switch (sortKey) {
        case 'model_name':
          return dir * a.model_name.localeCompare(b.model_name);
        case 'kv':
          return (
            dir *
            kvLabel(a.kv_type_k, a.kv_type_v).localeCompare(
              kvLabel(b.kv_type_k, b.kv_type_v),
            )
          );
        case 'agent_version':
          return dir * a.agent_version.localeCompare(b.agent_version);
        case 'resolved':
          return dir * (a.resolved - b.resolved);
        case 'total':
          return dir * (a.total - b.total);
        case 'rate':
          return dir * (a.rate - b.rate);
        case 'delta': {
          const da = deltaBaseline(a, allRows) ?? -999;
          const db = deltaBaseline(b, allRows) ?? -999;
          return dir * (da - db);
        }
        default:
          return 0;
      }
    });
    return copy;
  }, [rows, allRows, sortKey, sortDir]);

  const [copied, setCopied] = useState(false);

  const buildTableData = useCallback(() => {
    const headers = ['Model', 'KV', 'Agent', 'Resolved', 'Total', 'Rate', 'Delta (f16)'];
    const dataRows = sorted.map((row) => {
      const delta = deltaBaseline(row, allRows);
      return [
        row.model_name,
        kvLabel(row.kv_type_k, row.kv_type_v),
        `${row.agent_branch} ${row.agent_version}`,
        String(row.resolved),
        String(row.total),
        fmtPct(row.rate),
        fmtDelta(delta),
      ];
    });
    return { headers, dataRows };
  }, [sorted, allRows]);

  function handleCopyMarkdown() {
    const { headers, dataRows } = buildTableData();
    const sep = headers.map(() => '---');
    const lines = [
      `| ${headers.join(' | ')} |`,
      `| ${sep.join(' | ')} |`,
      ...dataRows.map((r) => `| ${r.join(' | ')} |`),
    ];
    navigator.clipboard.writeText(lines.join('\n')).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  function handleExportCsv() {
    const { headers, dataRows } = buildTableData();
    const escape = (v: string) => (v.includes(',') || v.includes('"') ? `"${v.replace(/"/g, '""')}"` : v);
    const lines = [
      headers.map(escape).join(','),
      ...dataRows.map((r) => r.map(escape).join(',')),
    ];
    const blob = new Blob([lines.join('\n')], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'leaderboard.csv';
    a.click();
    URL.revokeObjectURL(url);
  }

  function thClass(key: SortKey) {
    return sortKey === key
      ? 'leaderboard-table th--sorted'
      : undefined;
  }

  function arrow(key: SortKey) {
    if (sortKey !== key) return '';
    return sortDir === 'asc' ? ' \u25B2' : ' \u25BC';
  }

  return (
    <div>
      <div className="leaderboard-table__actions">
        <button className="leaderboard-table__btn" onClick={handleCopyMarkdown}>
          {copied ? 'Copied!' : 'Copy as Markdown'}
        </button>
        <button className="leaderboard-table__btn" onClick={handleExportCsv}>
          Export CSV
        </button>
      </div>
      <table className="leaderboard-table">
      <thead>
        <tr>
          <th className={thClass('model_name')} onClick={() => handleSort('model_name')}>
            Model{arrow('model_name')}
          </th>
          <th className={thClass('kv')} onClick={() => handleSort('kv')}>
            KV{arrow('kv')}
          </th>
          <th className={thClass('agent_version')} onClick={() => handleSort('agent_version')}>
            Agent{arrow('agent_version')}
          </th>
          <th className={thClass('resolved')} onClick={() => handleSort('resolved')}>
            Resolved{arrow('resolved')}
          </th>
          <th className={thClass('total')} onClick={() => handleSort('total')}>
            Total{arrow('total')}
          </th>
          <th className={thClass('rate')} onClick={() => handleSort('rate')}>
            Rate{arrow('rate')}
          </th>
          <th className={thClass('delta')} onClick={() => handleSort('delta')}>
            Delta (f16){arrow('delta')}
          </th>
        </tr>
      </thead>
      <tbody>
        {sorted.map((row) => {
          const delta = deltaBaseline(row, allRows);
          const deltaClass =
            delta === null || delta === 0
              ? 'leaderboard-table__delta--neutral'
              : delta > 0
                ? 'leaderboard-table__delta--positive'
                : 'leaderboard-table__delta--negative';

          return (
            <tr
              key={row.run_id}
              onClick={() => navigate(`/run/${encodeURIComponent(row.run_id)}`)}
            >
              <td className="leaderboard-table__model">{row.model_name}</td>
              <td className="leaderboard-table__kv">
                {kvLabel(row.kv_type_k, row.kv_type_v)}
              </td>
              <td className="leaderboard-table__agent">{row.agent_branch} {row.agent_version}</td>
              <td>{row.resolved}</td>
              <td>{row.total}</td>
              <td className="leaderboard-table__rate">{fmtPct(row.rate)}</td>
              <td className={deltaClass}>{fmtDelta(delta)}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
    </div>
  );
}
