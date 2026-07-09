import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { authApi, organizationsApi } from '../api';
import {
  clearTokens,
  enableOrgScoping,
  getAccessToken,
  getScopedOrgId,
  setScopedOrgId,
  setTokens,
} from '../api/client';
import type { Organization, User, UserRole } from '../types';

interface AuthContextValue {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  /** true if the user's role is at least as powerful as `role` */
  hasRole: (role: UserRole) => boolean;
  // Super admin organization scope
  organizations: Organization[];
  scopedOrgId: number | null;
  setOrgScope: (orgId: number | null) => void;
}

const ROLE_RANK: Record<UserRole, number> = {
  viewer: 0,
  operator: 1,
  admin: 2,
  super_admin: 3,
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [scopedOrgId, setScopedOrgIdState] = useState<number | null>(getScopedOrgId());

  const bootstrapSuperAdmin = useCallback(async (me: User) => {
    enableOrgScoping(true);
    try {
      const page = await organizationsApi.list({ limit: 200 });
      setOrganizations(page.items);
      const stored = getScopedOrgId();
      const valid = page.items.some((o) => o.id === stored);
      if (!valid) {
        const fallback = me.organization_id ?? page.items[0]?.id ?? null;
        setScopedOrgId(fallback);
        setScopedOrgIdState(fallback);
      }
    } catch {
      // organizations list failed; keep whatever scope is stored
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function bootstrap() {
      if (!getAccessToken()) {
        setLoading(false);
        return;
      }
      try {
        const me = await authApi.me();
        if (cancelled) return;
        setUser(me);
        if (me.role === 'super_admin') {
          await bootstrapSuperAdmin(me);
        } else {
          enableOrgScoping(false);
        }
      } catch {
        if (!cancelled) clearTokens();
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void bootstrap();
    return () => {
      cancelled = true;
    };
  }, [bootstrapSuperAdmin]);

  const login = useCallback(
    async (email: string, password: string) => {
      const pair = await authApi.login(email, password);
      setTokens(pair);
      const me = await authApi.me();
      if (me.role === 'super_admin') {
        await bootstrapSuperAdmin(me);
      } else {
        enableOrgScoping(false);
      }
      setUser(me);
    },
    [bootstrapSuperAdmin],
  );

  const logout = useCallback(() => {
    clearTokens();
    setScopedOrgId(null);
    enableOrgScoping(false);
    setUser(null);
    window.location.href = '/login';
  }, []);

  const hasRole = useCallback(
    (role: UserRole) => (user ? ROLE_RANK[user.role] >= ROLE_RANK[role] : false),
    [user],
  );

  const setOrgScope = useCallback((orgId: number | null) => {
    setScopedOrgId(orgId);
    setScopedOrgIdState(orgId);
    // Full reload keeps every page's data consistent with the new tenant.
    window.location.reload();
  }, []);

  const value = useMemo(
    () => ({ user, loading, login, logout, hasRole, organizations, scopedOrgId, setOrgScope }),
    [user, loading, login, logout, hasRole, organizations, scopedOrgId, setOrgScope],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
