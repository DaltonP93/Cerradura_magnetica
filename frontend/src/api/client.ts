import axios, { AxiosError, type InternalAxiosRequestConfig } from 'axios';
import type { TokenPair } from '../types';

const BASE_URL: string = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? '';
export const API_PREFIX = '/api/v1';

// ---- Token storage ----
const ACCESS_KEY = 'cerradura.access_token';
const REFRESH_KEY = 'cerradura.refresh_token';
const ORG_KEY = 'cerradura.organization_id';

export function getAccessToken(): string | null {
  return localStorage.getItem(ACCESS_KEY);
}
export function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_KEY);
}
export function setTokens(pair: TokenPair): void {
  localStorage.setItem(ACCESS_KEY, pair.access_token);
  localStorage.setItem(REFRESH_KEY, pair.refresh_token);
}
export function clearTokens(): void {
  localStorage.removeItem(ACCESS_KEY);
  localStorage.removeItem(REFRESH_KEY);
}

// ---- Organization scope (super admin) ----
export function getScopedOrgId(): number | null {
  const raw = localStorage.getItem(ORG_KEY);
  if (raw == null) return null;
  const n = Number(raw);
  return Number.isFinite(n) ? n : null;
}
export function setScopedOrgId(orgId: number | null): void {
  if (orgId == null) localStorage.removeItem(ORG_KEY);
  else localStorage.setItem(ORG_KEY, String(orgId));
}

let orgScopingEnabled = false;
/** Enabled only for super admins; appends ?organization_id= to data endpoints. */
export function enableOrgScoping(enabled: boolean): void {
  orgScopingEnabled = enabled;
}

export const api = axios.create({ baseURL: BASE_URL + API_PREFIX });

// Endpoints that must never carry the organization_id query param.
const UNSCOPED = [/^\/auth\//, /^\/organizations/];

api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = getAccessToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  const url = config.url ?? '';
  if (orgScopingEnabled && !UNSCOPED.some((re) => re.test(url))) {
    const orgId = getScopedOrgId();
    if (orgId != null) {
      config.params = { ...(config.params as Record<string, unknown> | undefined), organization_id: orgId };
    }
  }
  return config;
});

// ---- 401 -> refresh once -> retry ----
let refreshPromise: Promise<string | null> | null = null;

async function tryRefresh(): Promise<string | null> {
  const refreshToken = getRefreshToken();
  if (!refreshToken) return null;
  try {
    const { data } = await axios.post<TokenPair>(`${BASE_URL}${API_PREFIX}/auth/refresh`, {
      refresh_token: refreshToken,
    });
    setTokens(data);
    return data.access_token;
  } catch {
    return null;
  }
}

function redirectToLogin(): void {
  clearTokens();
  if (!window.location.pathname.startsWith('/login')) {
    window.location.href = '/login';
  }
}

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const original = error.config as (InternalAxiosRequestConfig & { _retried?: boolean }) | undefined;
    const status = error.response?.status;
    const url = original?.url ?? '';
    const isAuthCall = url.startsWith('/auth/login') || url.startsWith('/auth/refresh');

    if (status === 401 && original && !original._retried && !isAuthCall) {
      original._retried = true;
      refreshPromise = refreshPromise ?? tryRefresh().finally(() => setTimeout(() => (refreshPromise = null), 0));
      const newToken = await refreshPromise;
      if (newToken) {
        original.headers.Authorization = `Bearer ${newToken}`;
        return api.request(original);
      }
      redirectToLogin();
    }
    return Promise.reject(error);
  },
);

/** Extract a human-readable message from an API error. */
export function apiErrorMessage(err: unknown): string {
  if (axios.isAxiosError(err)) {
    const detail = (err.response?.data as { detail?: unknown } | undefined)?.detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) {
      // FastAPI validation errors
      return detail
        .map((d: { loc?: unknown[]; msg?: string }) => {
          const loc = Array.isArray(d.loc) ? d.loc.slice(1).join('.') : '';
          return loc ? `${loc}: ${d.msg ?? ''}` : d.msg ?? '';
        })
        .join('; ');
    }
    if (err.response) return `Error ${err.response.status}`;
    return 'No se pudo conectar con el servidor';
  }
  return 'Error inesperado';
}

/** Build the WebSocket URL for the live event stream. */
export function buildEventsWsUrl(): string | null {
  const token = getAccessToken();
  if (!token) return null;
  let base: string;
  if (BASE_URL) {
    base = BASE_URL.replace(/^http/, 'ws');
  } else {
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    base = `${proto}//${window.location.host}`;
  }
  let url = `${base}/ws/events?token=${encodeURIComponent(token)}`;
  if (orgScopingEnabled) {
    const orgId = getScopedOrgId();
    if (orgId != null) url += `&organization_id=${orgId}`;
  }
  return url;
}
