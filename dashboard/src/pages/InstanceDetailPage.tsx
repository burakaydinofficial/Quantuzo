import { useParams, Link } from 'react-router-dom';
import { usePredictions } from '../hooks/usePredictions';
import { useTrajectory } from '../hooks/useTrajectory';
import { PatchDiffViewer } from '../components/instance-detail/PatchDiffViewer';
import { TrajectoryViewer } from '../components/instance-detail/TrajectoryViewer';
import { LoadingSpinner } from '../components/shared/LoadingSpinner';
import { ErrorBanner } from '../components/shared/ErrorBanner';
import './InstanceDetailPage.css';

export function InstanceDetailPage() {
  const { runId, instanceId } = useParams<{
    runId: string;
    instanceId: string;
  }>();
  const {
    data: predictions,
    loading: predLoading,
    error: predError,
  } = usePredictions(runId);
  const {
    data: trajectory,
    loading: trajLoading,
    error: trajError,
  } = useTrajectory(runId, instanceId);

  const patch = predictions && instanceId ? predictions[instanceId]?.model_patch ?? '' : '';

  if (predLoading || trajLoading) return <LoadingSpinner />;

  return (
    <div className="instance-detail">
      <div className="instance-detail__header">
        <Link
          to={`/run/${encodeURIComponent(runId!)}`}
          className="instance-detail__back"
        >
          &larr; Run Detail
        </Link>
        <h1 className="instance-detail__title">{instanceId}</h1>
      </div>

      {predError && <ErrorBanner message={predError} />}

      <h2 className="instance-detail__section-title">Patch</h2>
      <PatchDiffViewer patch={patch} />

      {trajError && <ErrorBanner message={trajError} />}

      {trajectory && (
        <>
          <h2 className="instance-detail__section-title">Agent Trajectory</h2>
          <TrajectoryViewer data={trajectory} />
        </>
      )}
    </div>
  );
}
