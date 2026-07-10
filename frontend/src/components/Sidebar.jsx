import { NavLink } from "react-router-dom";
import { LayoutGrid, Users, FileCheck2, Settings as SettingsIcon, ScanLine } from "lucide-react";

const HR_LINKS = [
  { to: "/dashboard", label: "Dashboard", icon: LayoutGrid },
  { to: "/candidates", label: "Candidates", icon: Users },
  { to: "/settings", label: "Settings", icon: SettingsIcon },
];

const CANDIDATE_LINKS = [
  { to: "/portal", label: "My Documents", icon: ScanLine },
  { to: "/settings", label: "Settings", icon: SettingsIcon },
];

export default function Sidebar({ role }) {
  const links = role === "hr" ? HR_LINKS : CANDIDATE_LINKS;

  return (
    <aside className="hidden md:flex w-64 shrink-0 flex-col bg-surface-panel border-r border-surface-border px-4 py-6">
      <div className="mb-8 px-2">
        <div className="text-xl font-bold tracking-wide text-white">Onboarding<span className="text-accent">Verify</span></div>
        <div className="text-xs text-slate-400 mt-1">Document Verification Pipeline</div>
      </div>

      <nav className="flex flex-col gap-1">
        {links.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              `flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors ${
                isActive
                  ? "bg-accent text-white"
                  : "text-slate-300 hover:bg-surface-card hover:text-white"
              }`
            }
          >
            <Icon size={18} />
            {label}
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}
