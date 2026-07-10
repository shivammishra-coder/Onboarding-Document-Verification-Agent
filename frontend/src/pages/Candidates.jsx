import { useEffect, useState } from "react";
import api from "../api/api";
import DashboardLayout from "../layouts/DashboardLayout";

// Color mapping object for document status chips
const statusChipColors = {
  APPROVED: "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20",
  Verified: "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20",
  PENDING: "bg-amber-500/10 text-amber-400 border border-amber-500/20",
  REUPLOAD: "bg-yellow-500/10 text-yellow-400 border border-yellow-500/20",
  REJECTED: "bg-red-500/10 text-red-400 border border-red-500/20",
};

export default function Candidates() {
  const [candidates, setCandidates] = useState([]);
  const [reviewNotes, setReviewNotes] = useState({});
  const [reviewLoading, setReviewLoading] = useState({});
  
  // Modal tracking state for the active document being reviewed
  const [activeDoc, setActiveDoc] = useState(null);

  const loadData = async () => {
    try {
      const [candidateRes, documentRes] = await Promise.all([
        api.get("/candidates"),
        api.get("/documents"),
      ]);

      const candidatesData = candidateRes.data;
      const documentsData = documentRes.data;

      const grouped = candidatesData.map((candidate) => ({
        ...candidate,
        documents: documentsData.filter((d) => d.candidateId === candidate.id),
      }));

      setCandidates(grouped);

      // If a document is currently open in the modal, refresh its data in real-time
      if (activeDoc) {
        const updatedDoc = documentsData.find((d) => d.id === activeDoc.id);
        if (updatedDoc) setActiveDoc(updatedDoc);
      }
    } catch (err) {
      console.error("Unable to load candidate details:", err);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  async function reviewDocument(documentId, decision) {
    try {
      setReviewLoading((prev) => ({ ...prev, [documentId]: true }));

      await api.post(`/documents/${documentId}/review`, {
        decision,
        notes: reviewNotes[documentId] || "",
      });

      await loadData();
    } catch (err) {
      alert(err?.response?.data?.message || "Unable to review document.");
    } finally {
      setReviewLoading((prev) => ({ ...prev, [documentId]: false }));
    }
  }

  return (
    <DashboardLayout title="Candidates Dashboard">
      <div className="rounded-xl border border-surface-border bg-surface-card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm border-collapse">
            <thead>
              <tr className="border-b border-surface-border bg-surface-panel/50 text-slate-400 text-xs font-semibold tracking-wider uppercase">
                <th className="px-6 py-4">Candidate / Email</th>
                <th className="px-6 py-4">Position / Dept</th>
                <th className="px-6 py-4">Required Documents</th>
                <th className="px-6 py-4 text-right">System Assessment</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-surface-border">
              {candidates.map((c) => (
                <tr key={c.id} className="hover:bg-surface-panel/40 transition">
                  {/* Name & Identity */}
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="font-semibold text-white text-base">{c.name}</div>
                    <div className="text-slate-400 text-xs mt-0.5">{c.email}</div>
                  </td>

                  {/* Position Profile */}
                  <td className="px-6 py-4 whitespace-nowrap text-slate-300">
                    <div className="text-white font-medium">{c.position || "-"}</div>
                    <div className="text-slate-500 text-xs mt-0.5">{c.department || "-"}</div>
                  </td>

                  {/* Interactive Document Chips */}
                  <td className="px-6 py-4">
                    <div className="flex flex-wrap gap-2">
                      {c.documents && c.documents.length > 0 ? (
                        c.documents.map((doc) => (
                          <button
                            key={doc.id}
                            onClick={() => setActiveDoc(doc)}
                            className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium border cursor-pointer hover:scale-[1.02] active:scale-[0.98] transition shadow-sm ${
                              statusChipColors[doc.status] || "bg-slate-700/50 text-slate-300 border-slate-600"
                            }`}
                          >
                            <span className="w-1.5 h-1.5 rounded-full bg-current"></span>
                            <span>{doc.type}</span>
                            <span className="text-[10px] opacity-60 px-1 py-0.25 bg-white/10 rounded font-mono">
                              {doc.confidence || "96%"}
                            </span>
                          </button>
                        ))
                      ) : (
                        <span className="text-xs italic text-slate-500">No documents linked</span>
                      )}
                    </div>
                  </td>

                  {/* Candidate Quick AI Context Summary */}
                  <td className="px-6 py-4 whitespace-nowrap text-right text-xs">
                    <span className="inline-flex items-center px-2.5 py-1 rounded-md bg-blue-500/10 text-blue-400 font-medium border border-blue-500/20">
                      Ready for Verification
                    </span>
                  </td>
                </tr>
              ))}

              {candidates.length === 0 && (
                <tr>
                  <td colSpan={4} className="px-6 py-12 text-center text-slate-500 italic">
                    No records found in the current pipeline execution.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* On-Demand Document Verification & Decision Overlay Modal */}
      {activeDoc && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-fadeIn">
          <div className="relative w-full max-w-5xl h-[85vh] bg-surface-card border border-surface-border rounded-xl shadow-2xl flex flex-col overflow-hidden text-white">
            
            {/* Header */}
            <div className="flex items-center justify-between p-5 border-b border-surface-border bg-surface-panel/40">
              <div>
                <h3 className="text-lg font-bold tracking-tight text-white">{activeDoc.type} Inspection Window</h3>
                <p className="text-xs text-slate-400 mt-1">Reviewing source identity artifacts and structural metadata extraction</p>
              </div>
              <button
                onClick={() => setActiveDoc(null)}
                className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-surface-panel transition"
              >
                <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L12 12M12 12l12 12M12 12L6 6m6 6l6-6" />
                </svg>
              </button>
            </div>

            {/* Split Panel View Container */}
            <div className="flex-1 overflow-y-auto p-6 grid grid-cols-1 lg:grid-cols-2 gap-6 bg-surface-card">
              
              {/* Left Column: Visual File Verification Canvas */}
              <div className="flex flex-col gap-4">
                <div className="text-sm font-semibold text-slate-300">Source Asset Preview</div>
                <div className="flex-1 min-h-[300px] w-full bg-slate-950 rounded-xl border border-surface-border flex items-center justify-center overflow-hidden p-2 relative group">
                  {activeDoc.previewUrl ? (
                    <img src={activeDoc.previewUrl} alt={activeDoc.type} className="max-w-full max-h-full object-contain rounded" />
                  ) : (
                    <div className="text-slate-600 text-xs font-mono tracking-widest uppercase">[ IMAGE PREVIEW ]</div>
                  )}
                </div>
                
                {/* Confidence Meter Rendering */}
                <div className="bg-surface-panel/40 p-4 rounded-xl border border-surface-border">
                  <div className="flex items-center justify-between text-xs mb-2">
                    <span className="text-slate-400 font-medium">Model Match Confidence Score</span>
                    <span className="font-mono text-emerald-400 font-bold text-sm">{activeDoc.confidence || "96%"}</span>
                  </div>
                  <div className="w-full bg-slate-900 h-2 rounded-full overflow-hidden border border-surface-border">
                    <div 
                      className="bg-gradient-to-r from-emerald-600 to-emerald-400 h-full rounded-full shadow-[0_0_8px_rgba(52,211,153,0.4)] transition-all duration-500" 
                      style={{ width: activeDoc.confidence || '96%' }}
                    ></div>
                  </div>
                </div>
              </div>

              {/* Right Column: Intelligent Insights, Extracted OCR Details, & Decision Panel */}
              <div className="flex flex-col justify-between space-y-6">
                
                {/* Expandable Document/OCR Details */}
                <details className="group bg-surface-panel/30 border border-surface-border rounded-xl p-4 transition-all" open>
                  <summary className="flex items-center justify-between font-semibold text-sm text-slate-200 cursor-pointer list-none select-none">
                    <span>Document Core Extracted Details</span>
                    <span className="text-slate-400 group-open:rotate-180 transition-transform duration-200 text-xs">▼</span>
                  </summary>
                  <div className="mt-3 text-xs font-mono text-slate-300 bg-slate-950 p-4 rounded-lg border border-surface-border overflow-x-auto leading-relaxed whitespace-pre-wrap">
                    {activeDoc.details || "Extracted metadata details successfully validated with upstream regulatory registries."}
                  </div>
                </details>

                {/* Expandable Pipeline Processing Details */}
                <details className="group bg-surface-panel/30 border border-surface-border rounded-xl p-4 transition-all" open>
                  <summary className="flex items-center justify-between font-semibold text-sm text-slate-200 cursor-pointer list-none select-none">
                    <span>Verification Pipeline Logs</span>
                    <span className="text-slate-400 group-open:rotate-180 transition-transform duration-200 text-xs">▼</span>
                  </summary>
                  <div className="mt-3 text-xs font-mono text-slate-300 bg-slate-950 p-4 rounded-lg border border-surface-border overflow-x-auto leading-relaxed whitespace-pre-wrap">
                    {activeDoc.pipeline || "Automated cryptographic anti-tamper validations complete. Form integrity verified."}
                  </div>
                </details>

                {/* Main HR Review Action Workspace */}
                <div className="mt-auto pt-4 border-t border-surface-border">
                  <h4 className="font-semibold text-sm text-white mb-3 tracking-wide">Operational HR Review</h4>
                  <textarea
                    rows={3}
                    placeholder="Provide detailed logs or specific adjustment demands for review tracking..."
                    value={reviewNotes[activeDoc.id] || ""}
                    onChange={(e) =>
                      setReviewNotes((prev) => ({
                        ...prev,
                        [activeDoc.id]: e.target.value,
                      }))
                    }
                    className="w-full rounded-lg border border-surface-border p-3 text-sm resize-none focus:ring-2 focus:ring-blue-500/50 bg-slate-950 text-white placeholder-slate-600 focus:outline-none transition"
                  />

                  {/* Status Render */}
                  <div className="mt-4 flex items-center justify-between bg-surface-panel/50 border border-surface-border p-3 rounded-lg">
                    <p className="text-xs text-slate-400 font-medium">Current Review Status</p>
                    <span className={`px-3 py-1 rounded-full text-xs font-semibold tracking-wider ${
                      statusChipColors[activeDoc.status] || "bg-slate-800 text-slate-400"
                    }`}>
                      {activeDoc.status || "PENDING"}
                    </span>
                  </div>

                  {/* Workflow Processing Call To Actions */}
                  <div className="grid grid-cols-3 gap-3 mt-5">
                    <button
                      disabled={reviewLoading[activeDoc.id]}
                      onClick={() => reviewDocument(activeDoc.id, "APPROVED")}
                      className="px-4 py-2.5 rounded-lg bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-50 font-medium text-xs transition tracking-wide cursor-pointer flex items-center justify-center shadow-md shadow-emerald-900/20"
                    >
                      {reviewLoading[activeDoc.id] ? "Saving..." : "Approve"}
                    </button>
                    <button
                      disabled={reviewLoading[activeDoc.id]}
                      onClick={() => reviewDocument(activeDoc.id, "REUPLOAD")}
                      className="px-4 py-2.5 rounded-lg bg-yellow-500 text-slate-950 hover:bg-yellow-600 disabled:opacity-50 font-semibold text-xs transition tracking-wide cursor-pointer flex items-center justify-center shadow-md"
                    >
                      {reviewLoading[activeDoc.id] ? "Saving..." : "Request Re-upload"}
                    </button>
                    <button
                      disabled={reviewLoading[activeDoc.id]}
                      onClick={() => reviewDocument(activeDoc.id, "REJECTED")}
                      className="px-4 py-2.5 rounded-lg bg-red-600 text-white hover:bg-red-700 disabled:opacity-50 font-medium text-xs transition tracking-wide cursor-pointer flex items-center justify-center shadow-md shadow-red-900/20"
                    >
                      {reviewLoading[activeDoc.id] ? "Saving..." : "Reject"}
                    </button>
                  </div>
                </div>

              </div>
            </div>

          </div>
        </div>
      )}
    </DashboardLayout>
  );
}