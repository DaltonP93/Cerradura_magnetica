import { Navigate, Route, Routes } from 'react-router-dom';
import { Layout } from './components/Layout';
import { ProtectedRoute } from './components/ProtectedRoute';
import { AccessLevelsPage } from './pages/AccessLevelsPage';
import { AuditPage } from './pages/AuditPage';
import { CardholdersPage } from './pages/CardholdersPage';
import { ControllersPage } from './pages/ControllersPage';
import { DashboardPage } from './pages/DashboardPage';
import { DepartmentsPage } from './pages/DepartmentsPage';
import { DoorsPage } from './pages/DoorsPage';
import { LoginPage } from './pages/LoginPage';
import { MonitoringPage } from './pages/MonitoringPage';
import { OrganizationsPage } from './pages/OrganizationsPage';
import { ReportsPage } from './pages/ReportsPage';
import { SchedulesPage } from './pages/SchedulesPage';
import { SitesPage } from './pages/SitesPage';
import { UsersPage } from './pages/UsersPage';

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        element={
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        }
      >
        <Route path="/" element={<DashboardPage />} />
        <Route path="/monitoreo" element={<MonitoringPage />} />
        <Route path="/controladores" element={<ControllersPage />} />
        <Route path="/puertas" element={<DoorsPage />} />
        <Route path="/personal" element={<CardholdersPage />} />
        <Route path="/departamentos" element={<DepartmentsPage />} />
        <Route path="/horarios" element={<SchedulesPage />} />
        <Route path="/niveles-acceso" element={<AccessLevelsPage />} />
        <Route path="/reportes" element={<ReportsPage />} />
        <Route path="/sitios" element={<SitesPage />} />
        <Route
          path="/auditoria"
          element={
            <ProtectedRoute minRole="admin">
              <AuditPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/usuarios"
          element={
            <ProtectedRoute minRole="admin">
              <UsersPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/organizaciones"
          element={
            <ProtectedRoute superAdminOnly>
              <OrganizationsPage />
            </ProtectedRoute>
          }
        />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
