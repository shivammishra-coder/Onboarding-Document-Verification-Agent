import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function Register() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({
    name: "",
    email: "",
    password: "",
    role: "candidate",
    position: "",
    department: "",
    dob: "",
  });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const user = await register(form);
      navigate(user.role === "hr" ? "/dashboard" : "/portal");
    } catch (err) {
      setError(err.response?.data?.message || "Registration failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-surface px-4 py-10">
      <div className="w-full max-w-md rounded-xl border border-surface-border bg-surface-card p-8">
        <div className="mb-6 text-center">
          <div className="text-2xl font-bold text-white">
            Onboarding<span className="text-accent">Verify</span>
          </div>
          <p className="mt-1 text-sm text-slate-400">Create your account</p>
        </div>

        {error && (
          <div className="mb-4 rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-sm text-danger">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Role toggle */}
          <div className="grid grid-cols-2 gap-2">
            {["candidate", "hr"].map((r) => (
              <button
                type="button"
                key={r}
                onClick={() => setForm({ ...form, role: r })}
                className={`rounded-lg border py-2 text-sm font-medium capitalize transition-colors ${
                  form.role === r
                    ? "border-accent bg-accent/10 text-accent"
                    : "border-surface-border text-slate-300 hover:bg-surface-panel"
                }`}
              >
                {r === "hr" ? "HR Team" : "Candidate"}
              </button>
            ))}
          </div>

          <Field label="Full name" value={form.name} onChange={(v) => setForm({ ...form, name: v })} required />
          <Field label="Email" type="email" value={form.email} onChange={(v) => setForm({ ...form, email: v })} required />
          <Field label="Password" type="password" value={form.password} onChange={(v) => setForm({ ...form, password: v })} required />

          {form.role === "candidate" && (
            <>
              <Field label="Date of birth" type="date" value={form.dob} onChange={(v) => setForm({ ...form, dob: v })} />
              <Field label="Position applied for" value={form.position} onChange={(v) => setForm({ ...form, position: v })} />
              <Field label="Department" value={form.department} onChange={(v) => setForm({ ...form, department: v })} />
            </>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-lg bg-accent py-2.5 text-sm font-semibold text-white transition-colors hover:bg-accent-hover disabled:opacity-60"
          >
            {loading ? "Creating account..." : "Create account"}
          </button>
        </form>

        <p className="mt-6 text-center text-sm text-slate-400">
          Already have an account?{" "}
          <Link to="/login" className="font-medium text-accent hover:underline">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  );
}

function Field({ label, type = "text", value, onChange, required }) {
  return (
    <div>
      <label className="mb-1 block text-sm text-slate-300">{label}</label>
      <input
        type={type}
        required={required}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-lg border border-surface-border bg-surface-panel px-3 py-2 text-sm text-white outline-none focus:border-accent"
      />
    </div>
  );
}
