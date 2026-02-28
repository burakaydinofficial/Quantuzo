import { NavLink, Outlet } from 'react-router-dom';
import './AppShell.css';

function navLinkClass({ isActive }: { isActive: boolean }) {
  return isActive
    ? 'app-shell__nav-link app-shell__nav-link--active'
    : 'app-shell__nav-link';
}

export function AppShell() {
  return (
    <div className="app-shell">
      <nav className="app-shell__nav">
        <NavLink to="/" className="app-shell__logo">
          Quantuzo
        </NavLink>
        <div className="app-shell__nav-links">
          <NavLink to="/" end className={navLinkClass}>
            Leaderboard
          </NavLink>
          <NavLink to="/compare" className={navLinkClass}>
            Compare
          </NavLink>
        </div>
      </nav>
      <main className="app-shell__content">
        <Outlet />
      </main>
      <footer className="app-shell__footer">
        KV Cache Quantization Benchmark &middot;{' '}
        <a
          href="https://github.com/burakaydinofficial/Quantuzo"
          target="_blank"
          rel="noreferrer"
        >
          GitHub
        </a>{' '}
        &middot;{' '}
        <a
          href="https://huggingface.co/datasets/burakaydinofficial/Quantuzo"
          target="_blank"
          rel="noreferrer"
        >
          Dataset
        </a>
      </footer>
    </div>
  );
}
