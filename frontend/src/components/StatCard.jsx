/**
 * Mirrors the "License Utilization" cards in the reference dashboard:
 * icon + title, a status pill, big numbers, and a progress bar.
 */
export default function StatCard({ icon, title, subtitle, statusLabel, statusColor = "text-success", value, total, extraRows = [] }) {
  const pct = total ? Math.round((value / total) * 100) : 0;

  return (
    <div className="rounded-xl border border-surface-border bg-surface-card p-5">
      <div className="flex items-start gap-3">
        {icon && <div className="text-2xl">{icon}</div>}
        <div>
          <div className="font-semibold text-white">{title}</div>
          {subtitle && <div className="text-xs text-slate-400">{subtitle}</div>}
        </div>
      </div>

      {statusLabel && <div className={`mt-3 text-sm font-medium ${statusColor}`}>{statusLabel}</div>}

      <div className="mt-4 space-y-1 text-sm text-slate-300">
        {extraRows.map((row) => (
          <div key={row.label} className="flex justify-between">
            <span>{row.label}</span>
            <span className="font-semibold text-white">{row.value}</span>
          </div>
        ))}
      </div>

      {total !== undefined && (
        <div className="mt-4">
          <div className="h-2 w-full overflow-hidden rounded-full bg-surface-panel">
            <div className="h-full rounded-full bg-accent" style={{ width: `${pct}%` }} />
          </div>
          <div className="mt-1 text-xs text-slate-400">{pct}% of total</div>
        </div>
      )}
    </div>
  );
}
