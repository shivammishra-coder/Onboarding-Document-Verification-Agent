import Sidebar from "../components/Sidebar";
import Topbar from "../components/Topbar";
import { useAuth } from "../context/AuthContext";

export default function DashboardLayout({ title, children }) {
  const { user } = useAuth();

  return (
    <div className="flex h-screen bg-surface">
      <Sidebar role={user?.role} />
      <div className="flex flex-1 flex-col overflow-hidden">
        <Topbar title={title} />
        <main className="flex-1 overflow-y-auto p-6">{children}</main>
      </div>
    </div>
  );
}
