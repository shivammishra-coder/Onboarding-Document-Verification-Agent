import { useEffect, useState } from "react";
import api from "../api/api";
import DashboardLayout from "../layouts/DashboardLayout";
import StatusBadge from "../components/StatusBadge";
import { Check, X, RotateCcw } from "lucide-react";

const TABS = [
  { key: "ALL", label: "All Requests" },
  { key: "VERIFIED", label: "Verified" },
  { key: "NEEDS_ATTENTION", label: "Needs Attention" },
  { key: "REJECTED", label: "Rejected" },
];

export default function ReviewQueue() {
  const [docs, setDocs] = useState([]);
  const [activeTab, setActiveTab] = useState("ALL");
  const [selected, setSelected] = useState(null);
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function loadDocs() {
    const res = await api.get("/documents");
    setDocs(res.data);
  }

  useEffect(() => {
    loadDocs();
  }, []);

  const counts = {
    ALL: docs.length,
    VERIFIED: docs.filter((d) => d.status === "VERIFIED").length,
    NEEDS_ATTENTION: docs.filter((d) => d.status === "NEEDS_ATTENTION").length,
    REJECTED: docs.filter((d) => d.status === "REJECTED").length,
  };

  const filtered = activeTab === "ALL" ? docs : docs.filter((d) => d.status === activeTab);

  async function submitDecision(decision) {
    if (!selected) return;
    setSubmitting(true);
    try {
      await api.post(`/documents/${selected.id}/review`, { decision, notes });
      setSelected(null);
      setNotes("");
      await loadDocs();
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <DashboardLayout title="Review Queue — Human-in-the-Loop Final Check">
      {/* Summary tiles, mirroring the reference "Requests" screen */}
      <div className="mb-6 grid grid-cols-2 gap-4 sm:grid-cols-4">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setActiveTab(t.key)}
            className={`rounded-xl border p-4 text-left transition-colors ${
              activeTab === t.key
                ? "border-accent bg-accent/10"
                : "border-surface-border bg-surface-card hover:bg-surface-panel"
            }`}
          >
            <div className="text-xs text-slate-400">{t.label}</div>
            <div className="mt-1 text-2xl font-bold text-white">{counts[t.key]}</div>
          </button>
        ))}
      </div>

      <div className="rounded-xl border border-surface-border bg-surface-card">
        <div className="border-b border-surface-border px-6 py-4">
          <h2 className="text-base font-semibold text-white">Documents</h2>
        </div>
        <div className="divide-y divide-surface-border">
          {filtered.length === 0 && (
            <div className="px-6 py-8 text-center text-sm text-slate-400">No documents in this category.</div>
          )}
          {filtered.map((doc) => (
            <button
              key={doc.id}
              onClick={() => setSelected(doc)}
              className="flex w-full flex-col gap-1 px-6 py-4 text-left hover:bg-surface-panel sm:flex-row sm:items-center sm:justify-between"
            >
              <div>
                <div className="text-sm font-medium text-white">
                  {doc.candidateName} <span className="text-slate-400">— {doc.docType.replaceAll("_", " ")}</span>
                </div>
                <div className="text-xs text-slate-400">
                  {doc.originalName} • Confidence {Math.round((doc.pipelineResult?.decision?.confidence || 0) * 100)}%
                </div>
              </div>
              <div className="flex items-center gap-2">
                <StatusBadge status={doc.status} />
                <StatusBadge status={doc.hitlStatus} />
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* Review drawer */}
      {selected && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <div className="w-full max-w-lg rounded-xl border border-surface-border bg-surface-card p-6">
            <div className="mb-4 flex items-start justify-between">
              <div>
                <h3 className="text-lg font-semibold text-white">{selected.candidateName}</h3>
                <p className="text-xs text-slate-400">{selected.docType.replaceAll("_", " ")} • {selected.originalName}</p>
              </div>
              <StatusBadge status={selected.status} />
            </div>

            <div className="max-h-60 space-y-3 overflow-y-auto rounded-lg border border-surface-border bg-surface-panel p-4 text-sm">
              <Detail label="Classification confidence" value={`${Math.round(selected.pipelineResult.classification.confidence * 100)}%`} />
              <Detail label="OCR confidence" value={`${Math.round(selected.pipelineResult.ocr.ocrConfidence * 100)}%`} />
              <Detail label="Rule engine" value={selected.pipelineResult.ruleResult.passed ? "Passed" : "Issues found"} />
              <Detail label="AI semantic risk" value={`${Math.round(selected.pipelineResult.aiResult.semanticRisk * 100)}%`} />
              <Detail label="Fraud score" value={`${Math.round(selected.pipelineResult.fraudResult.fraudScore * 100)}%`} />
              <div>
                <div className="mb-1 text-slate-400">Decision reasons</div>
                <ul className="list-disc pl-5 text-slate-300">
                  {selected.pipelineResult.decision.reasons.map((r, i) => (
                    <li key={i}>{r}</li>
                  ))}
                </ul>
              </div>
            </div>

            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Reviewer notes (optional)"
              className="mt-4 w-full rounded-lg border border-surface-border bg-surface-panel px-3 py-2 text-sm text-white outline-none focus:border-accent"
              rows={2}
            />

            <div className="mt-4 flex gap-2">
              <button
                disabled={submitting}
                onClick={() => submitDecision("APPROVE")}
                className="flex flex-1 items-center justify-center gap-1 rounded-lg bg-success/15 py-2 text-sm font-semibold text-success hover:bg-success/25"
              >
                <Check size={15} /> Approve
              </button>
              <button
                disabled={submitting}
                onClick={() => submitDecision("REQUEST_REUPLOAD")}
                className="flex flex-1 items-center justify-center gap-1 rounded-lg bg-warning/15 py-2 text-sm font-semibold text-warning hover:bg-warning/25"
              >
                <RotateCcw size={15} /> Request Re-upload
              </button>
              <button
                disabled={submitting}
                onClick={() => submitDecision("REJECT")}
                className="flex flex-1 items-center justify-center gap-1 rounded-lg bg-danger/15 py-2 text-sm font-semibold text-danger hover:bg-danger/25"
              >
                <X size={15} /> Reject
              </button>
            </div>

            <button
              onClick={() => setSelected(null)}
              className="mt-3 w-full rounded-lg border border-surface-border py-2 text-sm text-slate-300 hover:bg-surface-panel"
            >
              Close
            </button>
          </div>
        </div>
      )}
    </DashboardLayout>
  );
}

function Detail({ label, value }) {
  return (
    <div className="flex justify-between">
      <span className="text-slate-400">{label}</span>
      <span className="font-medium text-white">{value}</span>
    </div>
  );
}
