import axios, { AxiosError, type InternalAxiosRequestConfig } from 'axios';

const BASE_URL: string = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? '';
export const API_PREFIX = '/api/v1';

// ---- Auth model ----
// The access and refresh JWTs live in HttpOnly cookies set by the server and
// are never accessible to JavaScript. The only auth value JS handles is the
// non-HttpOnly CSRF token, which we echo back on unsafe requests
// (double-submit). `withCredentials` makes the browser attach the cookies.
const CSRF_COOKIE = 'acp_csrf';
const CSRF_HEADER = 'X-CSRF-Token';
const UNSAFE_METHODS = new Set(['post', 'put', 'patch', 'delete']);

function readCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp('(?:^|; )' + name + '=([^;]*)'));
  return match ? decodeURIComponent(match[1]) : null;
}

// ---- Organization scope (super admin) ----
const ORG_KEY = 'cerradura.organization_id';

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

export const api = axios.create({ baseURL: BASE_URL + API_PREFIX, withCredentials: true });

// Endpoints that must never carry the organization_id query param.
const UNSCOPED = [/^\/auth\//, /^\/organizations/];

api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  // Cookies carry authentication automatically; here we only add the CSRF
  // double-submit header for state-changing requests.
  const method = (config.method ?? 'get').toLowerCase();
  if (UNSAFE_METHODS.has(method)) {
    const csrf = readCookie(CSRF_COOKIE);
    if (csrf) config.headers[CSRF_HEADER] = csrf;
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
let refreshPromise: Promise<boolean> | null = null;

async function tryRefresh(): Promise<boolean> {
  try {
    // The refresh token rides in its HttpOnly cookie; the body is empty.
    await axios.post(
      `${BASE_URL}${API_PREFIX}/auth/refresh`,
      {},
      { withCredentials: true, headers: csrfHeader() },
    );
    return true;
  } catch {
    return false;
  }
}

function csrfHeader(): Record<string, string> {
  const csrf = readCookie(CSRF_COOKIE);
  return csrf ? { [CSRF_HEADER]: csrf } : {};
}

function redirectToLogin(): void {
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
      const ok = await refreshPromise;
      if (ok) {
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

/**
 * Build the WebSocket URL for the live event stream. The socket authenticates
 * via the HttpOnly access cookie sent in the handshake, so no token travels in
 * the URL.
 */
export function buildEventsWsUrl(): string | null {
  let base: string;
  if (BASE_URL) {
    base = BASE_URL.replace(/^http/, 'ws');
  } else {
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    base = `${proto}//${window.location.host}`;
  }
  let url = `${base}/ws/events`;
  if (orgScopingEnabled) {
    const orgId = getScopedOrgId();
    if (orgId != null) url += `?organization_id=${orgId}`;
  }
  return url;
}
