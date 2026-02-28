import type { ProjectGroup } from '../../utils/project-parser';
import { fmtPct } from '../../utils/format';
import './ProjectBreakdownTable.css';

interface ProjectBreakdownTableProps {
  groups: ProjectGroup[];
}

export function ProjectBreakdownTable({ groups }: ProjectBreakdownTableProps) {
  return (
    <table className="project-breakdown">
      <thead>
        <tr>
          <th>Project</th>
          <th>Resolved</th>
          <th>Total</th>
          <th>Rate</th>
        </tr>
      </thead>
      <tbody>
        {groups.map((g) => (
          <tr key={g.project}>
            <td className="project-breakdown__project">{g.project}</td>
            <td>{g.resolved}</td>
            <td>{g.total}</td>
            <td className="project-breakdown__rate">{fmtPct(g.rate)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
