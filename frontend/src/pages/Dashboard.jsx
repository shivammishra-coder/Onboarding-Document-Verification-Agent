import { useEffect, useState } from "react";
import api from "../api/api";
import DashboardLayout from "../layouts/DashboardLayout";
import StatCard from "../components/StatCard";
import { Users, FileStack, ShieldCheck } from "lucide-react";

export default function Dashboard() {
  const [summary, setSummary] = useState(null);

  useEffect(() => {
    api.get("/dashboard/summary").then((res) => setSummary(res.data));
  }, []);

  if (!summary) {
    return (
      <DashboardLayout title="Enterprise Onboarding Verification Dashboard">
        <div className="text-slate-400">Loading dashboard...</div>
      </DashboardLayout>
    );
  }

  const total = summary.totalDocuments || 1; // avoid /0 in progress bars

  return (
    <DashboardLayout title="Enterprise Onboarding Verification Dashboard">
      {/* Top-level KPIs */}
      <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-3">
        <KpiCard icon={<Users size={20} />} label="Total Candidates" value={summary.totalCandidates} />
        <KpiCard icon={<FileStack size={20} />} label="Total Documents" value={summary.totalDocuments} />
        <KpiCard icon={<ShieldCheck size={20} />} label="Avg. Decision Confidence" value={`${Math.round(summary.avgConfidence * 100)}%`} />
      </div>

      <h2 className="mb-3 text-base font-semibold text-white">Document Verification Status</h2>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <StatCard
          title="Verified"
          subtitle="High confidence, no mismatch"
          statusLabel="Healthy"
          statusColor="text-success"
          value={summary.byStatus.VERIFIED}
          total={total}
          extraRows={[
            { label: "Documents", value: summary.byStatus.VERIFIED },
          ]}
        />
        <StatCard
          title="Needs Attention"
          subtitle="Missing docs, mismatches"
          statusLabel="Review required"
          statusColor="text-warning"
          value={summary.byStatus.NEEDS_ATTENTION}
          total={total}
          extraRows={[
            { label: "Documents", value: summary.byStatus.NEEDS_ATTENTION },
          ]}
        />
        <StatCard
          title="Rejected"
          subtitle="Fraud signals or hard failures"
          statusLabel="Blocked"
          statusColor="text-danger"
          value={summary.byStatus.REJECTED}
          total={total}
          extraRows={[
            { label: "Documents", value: summary.byStatus.REJECTED },
          ]}
        />
      </div>

      <div className="mt-6 rounded-xl border border-surface-border bg-surface-card p-5">
        <div className="flex items-center justify-between">
          <div>
            <div className="font-semibold text-white">Human-in-the-Loop Queue</div>
            <div className="text-xs text-slate-400">Every case (original and ambiguous) needs a manual final check</div>
          </div>
          <div className="text-2xl font-bold text-accent">{summary.pendingHitl}</div>
        </div>
      </div>
    </DashboardLayout>
  );
}

function KpiCard({ icon, label, value }) {
  return (
    <div className="flex items-center gap-4 rounded-xl border border-surface-border bg-surface-card p-5">
      <div className="rounded-lg bg-accent/15 p-3 text-accent">{icon}</div>
      <div>
        <div className="text-xs text-slate-400">{label}</div>
        <div className="text-xl font-bold text-white">{value}</div>
      </div>
    </div>
  );
}
