import { HashRouter, Routes, Route } from 'react-router-dom';
import { AppShell } from './components/layout/AppShell';
import { LeaderboardPage } from './pages/LeaderboardPage';
import { ModelComparisonPage } from './pages/ModelComparisonPage';
import { RunDetailPage } from './pages/RunDetailPage';
import { InstanceDetailPage } from './pages/InstanceDetailPage';
import './App.css';

export function App() {
  return (
    <HashRouter>
      <Routes>
        <Route element={<AppShell />}>
          <Route path="/" element={<LeaderboardPage />} />
          <Route path="/compare" element={<ModelComparisonPage />} />
          <Route path="/run/:runId" element={<RunDetailPage />} />
          <Route
            path="/run/:runId/instance/:instanceId"
            element={<InstanceDetailPage />}
          />
        </Route>
      </Routes>
    </HashRouter>
  );
}
