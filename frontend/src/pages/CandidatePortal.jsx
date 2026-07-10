import { useEffect, useRef, useState } from "react";
import { UploadCloud, RefreshCcw, FileText } from "lucide-react";
import api from "../api/api";
import DashboardLayout from "../layouts/DashboardLayout";
import StatusBadge from "../components/StatusBadge";

const DOC_TYPE_OPTIONS = [
  ["PAN_CARD", "PAN Card"],
  ["AADHAAR_CARD", "Aadhaar Card"],
  ["MARKSHEET", "Marksheet (10th/12th/Grad)"],
  ["DEGREE_CERTIFICATE", "Degree Certificate"],
  ["RESUME", "Detailed Resume"],
  ["OFFER_LETTER_PREVIOUS_ORG", "Previous Org Offer Letter"],
  ["PAYSLIP", "Last 3 Months Payslips"],
  ["RESIGNATION_ACCEPTANCE", "Resignation Acceptance / LWD Mail"],
  ["RELIEVING_LETTER", "Relieving & Experience Letter"],
  ["UAN_SCREENSHOT", "UAN History Screenshot"],
  ["PF_FORM_11", "PF Form 11"],
  ["SELF_DECLARATION_FORM", "Self Declaration Form"],
  ["PASSPORT_PHOTO", "Passport Photo"],
  ["GAP_DECLARATION_FORM", "Gap Declaration Form"],
  ["GAP_AFFIDAVIT", "Gap Affidavit"],
  ["CANCELLED_CHEQUE", "Cancelled Cheque"],
  ["SIGNED_OFFER_LETTER_JADE", "Signed Jade Global Offer Letter"],
];

export default function CandidatePortal() {
  const [docs, setDocs] = useState([]);
  const [declaredDocType, setDeclaredDocType] = useState(DOC_TYPE_OPTIONS[0][0]);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [reuploadTargetId, setReuploadTargetId] = useState(null);
  const fileInputRef = useRef(null);

  async function loadDocs() {
    const res = await api.get("/documents/mine");
    setDocs(res.data.sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt)));
  }

  useEffect(() => {
    loadDocs();
  }, []);

  async function handleFileChange(e) {
    const file = e.target.files[0];
    if (!file) return;
    setError("");
    setUploading(true);

    const formData = new FormData();
    formData.append("file", file);
    formData.append("declaredDocType", declaredDocType);

    try {
      if (reuploadTargetId) {
        await api.post(`/documents/${reuploadTargetId}/reupload`, formData);
        setReuploadTargetId(null);
      } else {
        await api.post("/documents/upload", formData);
      }
      await loadDocs();
    } catch (err) {
      setError(err.response?.data?.message || "Upload failed");
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  function triggerReupload(docId) {
    setReuploadTargetId(docId);
    fileInputRef.current?.click();
  }

  return (
    <DashboardLayout title="Candidate Document Portal">
      {/* Upload panel */}
      <div className="rounded-xl border border-surface-border bg-surface-card p-6">
        <h2 className="mb-1 text-base font-semibold text-white">Upload a document</h2>
        <p className="mb-4 text-sm text-slate-400">
          Files run automatically through classification, OCR, rule checks, AI validation, and fraud detection.
        </p>

        {error && (
          <div className="mb-4 rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-sm text-danger">{error}</div>
        )}

        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <select
            value={declaredDocType}
            onChange={(e) => setDeclaredDocType(e.target.value)}
            className="rounded-lg border border-surface-border bg-surface-panel px-3 py-2 text-sm text-white outline-none focus:border-accent"
          >
            {DOC_TYPE_OPTIONS.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>

          <label className="flex cursor-pointer items-center gap-2 rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-white hover:bg-accent-hover">
            <UploadCloud size={16} />
            {uploading ? "Uploading..." : "Choose file (PDF/JPG/PNG)"}
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.png,.jpg,.jpeg"
              className="hidden"
              onChange={handleFileChange}
              disabled={uploading}
            />
          </label>
        </div>
      </div>

      {/* Document list */}
      <div className="mt-6 rounded-xl border border-surface-border bg-surface-card">
        <div className="border-b border-surface-border px-6 py-4">
          <h2 className="text-base font-semibold text-white">My documents</h2>
        </div>

        <div className="divide-y divide-surface-border">
          {docs.length === 0 && (
            <div className="px-6 py-8 text-center text-sm text-slate-400">No documents uploaded yet.</div>
          )}
          {docs.map((doc) => (
            <div key={doc.id} className="flex flex-col gap-2 px-6 py-4 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex items-center gap-3">
                <FileText size={18} className="text-slate-400" />
                <div>
                  <div className="text-sm font-medium text-white">{doc.originalName}</div>
                  <div className="text-xs text-slate-400">
                    {doc.docType.replaceAll("_", " ")} • uploaded {new Date(doc.createdAt).toLocaleString()}
                  </div>
                </div>
              </div>

              <div className="flex items-center gap-3">
                <StatusBadge status={doc.status} />
                {doc.status !== "VERIFIED" && (
                  <button
                    onClick={() => triggerReupload(doc.id)}
                    className="flex items-center gap-1 rounded-lg border border-surface-border px-3 py-1.5 text-xs font-medium text-slate-200 hover:bg-surface-panel"
                  >
                    <RefreshCcw size={13} /> Re-upload
                  </button>
                )}
              </div>

              {doc.pipelineResult?.decision?.reasons?.length > 0 && doc.status !== "VERIFIED" && (
                <div className="sm:basis-full">
                  <ul className="mt-1 list-disc pl-5 text-xs text-slate-400">
                    {doc.pipelineResult.decision.reasons.map((r, i) => (
                      <li key={i}>{r}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </DashboardLayout>
  );
}
