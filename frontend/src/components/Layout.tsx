import { useState } from 'react';
import { NavLink, Outlet } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { ROLE_LABELS } from '../lib/format';
import type { UserRole } from '../types';

interface NavItem {
  to: string;
  label: string;
  icon: string;
  minRole?: UserRole;
  superAdminOnly?: boolean;
}

const NAV_SECTIONS: { title: string; items: NavItem[] }[] = [
  {
    title: 'Operación',
    items: [
      { to: '/', label: 'Panel', icon: '📊' },
      { to: '/monitoreo', label: 'Monitoreo en vivo', icon: '📡' },
      { to: '/reportes', label: 'Reportes de eventos', icon: '📄' },
    ],
  },
  {
    title: 'Infraestructura',
    items: [
      { to: '/sitios', label: 'Sitios', icon: '🏢' },
      { to: '/controladores', label: 'Controladores', icon: '🖥️' },
      { to: '/puertas', label: 'Puertas', icon: '🚪' },
    ],
  },
  {
    title: 'Personas y accesos',
    items: [
      { to: '/personal', label: 'Personal', icon: '👥' },
      { to: '/departamentos', label: 'Departamentos', icon: '🗂️' },
      { to: '/horarios', label: 'Horarios', icon: '🕒' },
      { to: '/niveles-acceso', label: 'Niveles de acceso', icon: '🔑' },
    ],
  },
  {
    title: 'Administración',
    items: [
      { to: '/auditoria', label: 'Auditoría', icon: '📋', minRole: 'admin' },
      { to: '/usuarios', label: 'Usuarios', icon: '🧑‍💼', minRole: 'admin' },
      { to: '/organizaciones', label: 'Organizaciones', icon: '🌐', superAdminOnly: true },
    ],
  },
];

export function Layout() {
  const { user, logout, hasRole, organizations, scopedOrgId, setOrgScope } = useAuth();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  if (!user) return null;

  const visibleSections = NAV_SECTIONS.map((section) => ({
    ...section,
    items: section.items.filter((item) => {
      if (item.superAdminOnly) return user.role === 'super_admin';
      if (item.minRole) return hasRole(item.minRole);
      return true;
    }),
  })).filter((s) => s.items.length > 0);

  const nav = (
    <nav className="flex-1 space-y-6 overflow-y-auto px-3 py-4">
      {visibleSections.map((section) => (
        <div key={section.title}>
          <p className="mb-2 px-3 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
            {section.title}
          </p>
          <ul className="space-y-0.5">
            {section.items.map((item) => (
              <li key={item.to}>
                <NavLink
                  to={item.to}
                  end={item.to === '/'}
                  onClick={() => setSidebarOpen(false)}
                  className={({ isActive }) =>
                    `flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition ${
                      isActive
                        ? 'bg-sky-500/15 font-medium text-sky-300'
                        : 'text-slate-400 hover:bg-slate-800/70 hover:text-slate-200'
                    }`
                  }
                >
                  <span aria-hidden="true">{item.icon}</span>
                  {item.label}
                </NavLink>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </nav>
  );

  return (
    <div className="flex min-h-screen bg-slate-950 text-slate-200">
      {/* Sidebar (desktop) */}
      <aside className="hidden w-64 flex-shrink-0 flex-col border-r border-slate-800 bg-slate-900/60 lg:flex">
        <div className="flex items-center gap-2 border-b border-slate-800 px-5 py-4">
          <span className="text-xl" aria-hidden="true">🔐</span>
          <div>
            <p className="text-sm font-bold tracking-tight text-white">Cerradura</p>
            <p className="text-[11px] text-slate-500">Control de acceso</p>
          </div>
        </div>
        {nav}
      </aside>

      {/* Sidebar (mobile overlay) */}
      {sidebarOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-slate-950/70" onClick={() => setSidebarOpen(false)} />
          <aside className="absolute inset-y-0 left-0 flex w-64 flex-col border-r border-slate-800 bg-slate-900">
            <div className="flex items-center justify-between border-b border-slate-800 px-5 py-4">
              <div className="flex items-center gap-2">
                <span className="text-xl" aria-hidden="true">🔐</span>
                <p className="text-sm font-bold text-white">Cerradura</p>
              </div>
              <button onClick={() => setSidebarOpen(false)} className="text-slate-400" aria-label="Cerrar menú">
                ✕
              </button>
            </div>
            {nav}
          </aside>
        </div>
      )}

      {/* Main */}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex items-center gap-4 border-b border-slate-800 bg-slate-950/90 px-4 py-3 backdrop-blur sm:px-6">
          <button
            onClick={() => setSidebarOpen(true)}
            className="rounded-md border border-slate-700 p-2 text-slate-300 lg:hidden"
            aria-label="Abrir menú"
          >
            ☰
          </button>

          {user.role === 'super_admin' && (
            <div className="flex items-center gap-2">
              <span className="hidden text-xs text-slate-500 sm:inline">Organización:</span>
              <select
                value={scopedOrgId ?? ''}
                onChange={(e) => setOrgScope(e.target.value ? Number(e.target.value) : null)}
                className="rounded-md border border-slate-600 bg-slate-800 px-2 py-1.5 text-sm text-slate-100 outline-none focus:border-sky-500"
                aria-label="Seleccionar organización"
              >
                {organizations.length === 0 && <option value="">Sin organizaciones</option>}
                {organizations.map((org) => (
                  <option key={org.id} value={org.id}>
                    {org.name}
                  </option>
                ))}
              </select>
            </div>
          )}

          <div className="ml-auto flex items-center gap-3">
            <div className="hidden text-right sm:block">
              <p className="text-sm font-medium text-slate-200">{user.full_name}</p>
              <p className="text-[11px] text-slate-500">{ROLE_LABELS[user.role]}</p>
            </div>
            <div className="flex h-9 w-9 items-center justify-center rounded-full bg-sky-600/30 text-sm font-semibold text-sky-300">
              {user.full_name
                .split(' ')
                .slice(0, 2)
                .map((p) => p[0]?.toUpperCase() ?? '')
                .join('')}
            </div>
            <button
              onClick={logout}
              className="rounded-md border border-slate-700 px-3 py-1.5 text-xs text-slate-300 transition hover:bg-slate-800"
            >
              Salir
            </button>
          </div>
        </header>

        <main className="flex-1 px-4 py-6 sm:px-6 lg:px-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

export function PageHeader({
  title,
  subtitle,
  actions,
}: {
  title: string;
  subtitle?: string;
  actions?: React.ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-white">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-slate-400">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}
