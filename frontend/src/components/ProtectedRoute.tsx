import type { ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { LoadingBlock } from './Spinner';
import type { UserRole } from '../types';

export function ProtectedRoute({
  children,
  minRole,
  superAdminOnly,
}: {
  children: ReactNode;
  minRole?: UserRole;
  superAdminOnly?: boolean;
}) {
  const { user, loading, hasRole } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-950">
        <LoadingBlock label="Verificando sesión…" />
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }

  if (superAdminOnly && user.role !== 'super_admin') {
    return <Navigate to="/" replace />;
  }

  if (minRole && !hasRole(minRole)) {
    return <Navigate to="/" replace />;
  }

  return <>{children}</>;
}
