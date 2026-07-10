import DashboardLayout from "../layouts/DashboardLayout";
import { useAuth } from "../context/AuthContext";

export default function Settings() {
  const { user } = useAuth();

  return (
    <DashboardLayout title="Settings">
      <div className="max-w-lg rounded-xl border border-surface-border bg-surface-card p-6">
        <h2 className="mb-4 text-base font-semibold text-white">Account</h2>
        <div className="space-y-3 text-sm">
          <Row label="Name" value={user?.name} />
          <Row label="Email" value={user?.email} />
          <Row label="Role" value={user?.role === "hr" ? "HR Team" : "Candidate"} />
        </div>
      </div>
    </DashboardLayout>
  );
}

function Row({ label, value }) {
  return (
    <div className="flex justify-between border-b border-surface-border pb-2">
      <span className="text-slate-400">{label}</span>
      <span className="font-medium text-white">{value}</span>
    </div>
  );
}
