import { useMemo } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useLeaderboard } from '../hooks/useLeaderboard';
import { useEvaluationResults } from '../hooks/useEvaluationResults';
import { RunSummaryCard } from '../components/run-detail/RunSummaryCard';
import { ExitStatusBar } from '../components/run-detail/ExitStatusBar';
import { ProjectBreakdownTable } from '../components/run-detail/ProjectBreakdownTable';
import { InstanceList } from '../components/run-detail/InstanceList';
import { LoadingSpinner } from '../components/shared/LoadingSpinner';
import { ErrorBanner } from '../components/shared/ErrorBanner';
import { groupByProject } from '../utils/project-parser';
import './RunDetailPage.css';

export function RunDetailPage() {
  const { runId } = useParams<{ runId: string }>();
  const { rows, loading: lbLoading } = useLeaderboard();
  const { data: evalResults, loading: evalLoading, error: evalError } =
    useEvaluationResults(runId);

  const row = useMemo(
    () => rows.find((r) => r.run_id === runId),
    [rows, runId],
  );

  const projectGroups = useMemo(() => {
    if (!evalResults?.instances) return [];
    const allIds = evalResults.instances.submitted_ids ?? [];
    const resolvedSet = new Set(evalResults.instances.resolved_ids ?? []);
    return groupByProject(allIds, resolvedSet);
  }, [evalResults]);

  if (lbLoading || evalLoading) return <LoadingSpinner />;
  if (evalError) return <ErrorBanner message={evalError} />;
  if (!row) {
    return <div className="run-detail__not-found">Run not found: {runId}</div>;
  }

  return (
    <div className="run-detail">
      <div className="run-detail__header">
        <Link to="/" className="run-detail__back">
          &larr; Leaderboard
        </Link>
        <h1 className="run-detail__title">{runId}</h1>
      </div>

      <RunSummaryCard row={row} allRows={rows} evalResults={evalResults} />

      {row.exit_statuses && <ExitStatusBar exitStatuses={row.exit_statuses} />}

      {projectGroups.length > 0 && (
        <>
          <h2 className="run-detail__section-title">Project Breakdown</h2>
          <ProjectBreakdownTable groups={projectGroups} />
        </>
      )}

      {evalResults?.instances && (
        <>
          <h2 className="run-detail__section-title">Instances</h2>
          <InstanceList instances={evalResults.instances} runId={runId!} />
        </>
      )}
    </div>
  );
}
