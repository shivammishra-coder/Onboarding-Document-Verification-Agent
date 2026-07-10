import { Navigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

/**
 * Wraps a page and redirects to /login if not authenticated,
 * or to the correct home page if the role doesn't match.
 */
export default function ProtectedRoute({ children, allowedRoles }) {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-surface text-slate-400">
        Loading...
      </div>
    );
  }

  if (!user) return <Navigate to="/login" replace />;

  if (allowedRoles && !allowedRoles.includes(user.role)) {
    return <Navigate to={user.role === "hr" ? "/dashboard" : "/portal"} replace />;
  }

  return children;
}
