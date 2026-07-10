import { Routes, Route, Navigate } from "react-router-dom";
import { useAuth } from "./context/AuthContext";
import ProtectedRoute from "./components/ProtectedRoute";

import Login from "./pages/Login";
import Register from "./pages/Register";
import Dashboard from "./pages/Dashboard";
import Candidates from "./pages/Candidates";
import CandidatePortal from "./pages/CandidatePortal";
import Settings from "./pages/Settings";

export default function App() {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-surface text-slate-400">
        Loading...
      </div>
    );
  }

  return (
    <Routes>
      <Route
        path="/login"
        element={user ? <Navigate to="/" /> : <Login />}
      />

      <Route
        path="/register"
        element={user ? <Navigate to="/" /> : <Register />}
      />

      {/* HR routes */}
      <Route
        path="/dashboard"
        element={
          <ProtectedRoute allowedRoles={["hr"]}>
            <Dashboard />
          </ProtectedRoute>
        }
      />

      <Route
        path="/candidates"
        element={
          <ProtectedRoute allowedRoles={["hr"]}>
            <Candidates />
          </ProtectedRoute>
        }
      />

      {/* Candidate routes */}
      <Route
        path="/portal"
        element={
          <ProtectedRoute allowedRoles={["candidate"]}>
            <CandidatePortal />
          </ProtectedRoute>
        }
      />

      {/* Shared */}
      <Route
        path="/settings"
        element={
          <ProtectedRoute>
            <Settings />
          </ProtectedRoute>
        }
      />

      <Route
        path="/"
        element={
          user ? (
            <Navigate
              to={user.role === "hr" ? "/dashboard" : "/portal"}
            />
          ) : (
            <Navigate to="/login" />
          )
        }
      />

      <Route path="*" element={<Navigate to="/" />} />
    </Routes>
  );
}