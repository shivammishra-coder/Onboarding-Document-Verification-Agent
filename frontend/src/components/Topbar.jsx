import { useState } from "react";
import { Bell, ChevronDown, LogOut } from "lucide-react";
import { useAuth } from "../context/AuthContext";

export default function Topbar({ title }) {
  const { user, logout } = useAuth();
  const [open, setOpen] = useState(false);

  const initials = (user?.name || "?")
    .split(" ")
    .map((p) => p[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();

  return (
    <header className="flex items-center justify-between border-b border-surface-border bg-surface px-6 py-4">
      <h1 className="text-lg font-semibold text-white">{title}</h1>

      <div className="flex items-center gap-4">
        <button className="relative rounded-full p-2 text-slate-300 hover:bg-surface-card">
          <Bell size={18} />
        </button>

        <div className="relative">
          <button
            onClick={() => setOpen((o) => !o)}
            className="flex items-center gap-2 rounded-full px-2 py-1 hover:bg-surface-card"
          >
            <span className="flex h-8 w-8 items-center justify-center rounded-full bg-accent text-xs font-semibold text-white">
              {initials}
            </span>
            <span className="text-sm text-slate-200">{user?.name}</span>
            <ChevronDown size={14} className="text-slate-400" />
          </button>

          {open && (
            <div className="absolute right-0 mt-2 w-44 rounded-lg border border-surface-border bg-surface-card shadow-lg">
              <button
                onClick={logout}
                className="flex w-full items-center gap-2 rounded-lg px-4 py-2.5 text-sm text-slate-200 hover:bg-surface-panel"
              >
                <LogOut size={16} /> Log out
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
