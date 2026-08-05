import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

export function Layout() {
  const { user, signOut } = useAuth();

  const navClass = ({ isActive }: { isActive: boolean }) =>
    `px-3 py-1.5 text-sm rounded transition-colors ${
      isActive ? "bg-accent-soft text-accent font-medium" : "text-ink-soft hover:text-ink"
    }`;

  return (
    <div className="min-h-screen flex flex-col">
      <header className="bg-surface border-b border-line">
        <div className="max-w-6xl mx-auto px-6 h-14 flex items-center gap-6">
          <NavLink to="/jobs" className="flex items-baseline gap-2 shrink-0">
            <span className="font-semibold text-ink tracking-tight">Screening</span>
            {/* The one place the amber shows in navigation: a reminder that
                everything this tool produces is provisional. */}
            <span className="eyebrow text-signal">advisory</span>
          </NavLink>

          <nav className="flex items-center gap-1">
            <NavLink to="/jobs" className={navClass}>Jobs</NavLink>
            <NavLink to="/search" className={navClass}>Search</NavLink>
          </nav>

          <div className="ml-auto flex items-center gap-3">
            <span className="text-xs text-ink-faint hidden sm:inline">
              {user?.email} · {user?.role}
            </span>
            <button onClick={signOut}
              className="text-sm text-ink-soft hover:text-ink px-2 py-1 rounded">
              Sign out
            </button>
          </div>
        </div>
      </header>

      <main className="flex-1 max-w-6xl w-full mx-auto px-6 py-8">
        <Outlet />
      </main>
    </div>
  );
}
