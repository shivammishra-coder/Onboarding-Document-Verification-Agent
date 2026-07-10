const STYLES = {
  VERIFIED: "bg-success/15 text-success border-success/30",
  NEEDS_ATTENTION: "bg-warning/15 text-warning border-warning/30",
  REJECTED: "bg-danger/15 text-danger border-danger/30",
  PENDING: "bg-slate-500/15 text-slate-300 border-slate-500/30",
  COMPLETED: "bg-accent/15 text-accent border-accent/30",
};

const LABELS = {
  VERIFIED: "Verified",
  NEEDS_ATTENTION: "Needs Attention",
  REJECTED: "Rejected",
  PENDING: "Pending",
  COMPLETED: "Completed",
};

export default function StatusBadge({ status }) {
  const cls = STYLES[status] || STYLES.PENDING;
  return (
    <span className={`inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-medium ${cls}`}>
      {LABELS[status] || status}
    </span>
  );
}
