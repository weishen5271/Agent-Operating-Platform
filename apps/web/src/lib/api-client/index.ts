import type {
  AdminKnowledgeResponse,
  AdminKnowledgeSourceDetailResponse,
  AdminKnowledgeBasesResponse,
  AdminPackagesResponse,
  AdminSecurityResponse,
  AdminSystemResponse,
  AdminTracesResponse,
  AdminWikiCompileRunsResponse,
  AdminWikiFileDistributionDetailResponse,
  AdminWikiFileDistributionResponse,
  AdminWikiPagesResponse,
  AdminWikiSearchResponse,
  AuthResponse,
  ChatCompletionResponse,
  DraftActionResponse,
  HomeSnapshot,
  LLMRuntimeConfig,
  KnowledgeIngestResponse,
  TenantListResponse,
  TenantProfile,
  TraceResponse,
  UserProfile,
  WikiCompileResponse,
} from "./types";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000/api/v1";

type AuthUserContext = {
  user_id: string;
  tenant_id: string;
  role?: string;
  email?: string;
  tenant_name?: string;
};

const AUTH_TOKEN_KEY = "auth_token";
const AUTH_USER_KEY = "auth_user";
const AUTH_EXPIRED_MESSAGE = "登录状态已失效，请重新登录。";

function decodeJwtPayload(token: string): Record<string, unknown> | null {
  if (typeof window === "undefined") {
    return null;
  }

  const segments = token.split(".");
  if (segments.length !== 3) {
    return null;
  }

  try {
    const base64 = segments[1].replace(/-/g, "+").replace(/_/g, "/");
    const padded = base64.padEnd(Math.ceil(base64.length / 4) * 4, "=");
    const json = window.atob(padded);
    return JSON.parse(json) as Record<string, unknown>;
  } catch {
    return null;
  }
}

function isTokenExpired(token: string): boolean {
  const payload = decodeJwtPayload(token);
  if (!payload) {
    return true;
  }

  const exp = payload.exp;
  if (typeof exp !== "number") {
    return true;
  }

  return exp * 1000 <= Date.now();
}

export function clearStoredAuth(): void {
  if (typeof window === "undefined") {
    return;
  }

  localStorage.removeItem(AUTH_TOKEN_KEY);
  localStorage.removeItem(AUTH_USER_KEY);
}

function redirectToLogin(): void {
  if (typeof window === "undefined") {
    return;
  }

  if (window.location.pathname !== "/login") {
    window.location.replace("/login");
  }
}

export function hasValidStoredAuth(): boolean {
  if (typeof window === "undefined") {
    return false;
  }

  const token = localStorage.getItem(AUTH_TOKEN_KEY);
  if (!token) {
    return false;
  }

  if (isTokenExpired(token)) {
    clearStoredAuth();
    return false;
  }

  return true;
}

function getAuthUserContext(): AuthUserContext | null {
  if (typeof window === "undefined") {
    return null;
  }

  const rawUser = localStorage.getItem(AUTH_USER_KEY);
  if (!rawUser) {
    return null;
  }

  try {
    const user = JSON.parse(rawUser) as Partial<AuthUserContext>;
    if (typeof user.user_id === "string" && typeof user.tenant_id === "string") {
      return {
        user_id: user.user_id,
        tenant_id: user.tenant_id,
        role: typeof user.role === "string" ? user.role : undefined,
        email: typeof user.email === "string" ? user.email : undefined,
        tenant_name: typeof user.tenant_name === "string" ? user.tenant_name : undefined,
      };
    }
  } catch {
    return null;
  }

  return null;
}

function withAuthContext(path: string): string {
  const url = new URL(`${API_BASE_URL}${path}`);
  const user = getAuthUserContext();
  if (user) {
    if (!url.searchParams.has("tenant_id")) {
      url.searchParams.set("tenant_id", user.tenant_id);
    }
    if (!url.searchParams.has("user_id")) {
      url.searchParams.set("user_id", user.user_id);
    }
  }
  return url.toString();
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const requiresBrowserAuth =
    path.startsWith("/admin") || path.startsWith("/workspace") || path.startsWith("/chat/actions");
  if (typeof window === "undefined" && requiresBrowserAuth) {
    throw new Error("Authenticated requests require browser context.");
  }

  const target = path.startsWith("/admin") || path.startsWith("/workspace") || path.startsWith("/chat/actions")
    ? withAuthContext(path)
    : `${API_BASE_URL}${path}`;

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init?.headers as Record<string, string> ?? {}),
  };

  // Add auth token if available
  if (typeof window !== "undefined") {
    const token = localStorage.getItem(AUTH_TOKEN_KEY);
    if (token) {
      if (isTokenExpired(token)) {
        clearStoredAuth();
        redirectToLogin();
        throw new Error(AUTH_EXPIRED_MESSAGE);
      }
      headers["Authorization"] = `Bearer ${token}`;
    }
  }

  const response = await fetch(target, {
    ...init,
    headers,
    cache: "no-store",
  });

  if (!response.ok) {
    let detail = "";
    try {
      const errorBody = (await response.json()) as { detail?: unknown };
      if (typeof errorBody.detail === "string") {
        detail = errorBody.detail;
      }
    } catch {
      detail = await response.text();
    }
    if (response.status === 401) {
      clearStoredAuth();
      if (!detail || detail.includes("认证令牌")) {
        redirectToLogin();
        throw new Error(AUTH_EXPIRED_MESSAGE);
      }
    }
    throw new Error(detail || `API request failed: ${response.status}`);
  }

  return (await response.json()) as T;
}

export function getHomeSnapshot(): Promise<HomeSnapshot> {
  return request<HomeSnapshot>("/workspace/home");
}

export function createChatCompletion(
  message: string,
  conversationId?: string,
  retrievalMode: "auto" | "rag" | "wiki" = "auto",
): Promise<ChatCompletionResponse> {
  return request<ChatCompletionResponse>("/chat/completions", {
    method: "POST",
    body: JSON.stringify({
      message,
      conversation_id: conversationId,
      retrieval_mode: retrievalMode,
    }),
  });
}

export function getTrace(traceId: string): Promise<TraceResponse> {
  return request<TraceResponse>(`/chat/traces/${traceId}`);
}

export function getAdminPackages(): Promise<AdminPackagesResponse> {
  return request<AdminPackagesResponse>("/admin/packages");
}

export function getAdminSystem(): Promise<AdminSystemResponse> {
  return request<AdminSystemResponse>("/admin/system");
}

export function getAdminSecurity(): Promise<AdminSecurityResponse> {
  return request<AdminSecurityResponse>("/admin/security");
}

export function getAdminKnowledge(knowledgeBaseCode?: string): Promise<AdminKnowledgeResponse> {
  const suffix = knowledgeBaseCode ? `?knowledge_base_code=${encodeURIComponent(knowledgeBaseCode)}` : "";
  return request<AdminKnowledgeResponse>(`/admin/knowledge${suffix}`);
}

export function getAdminKnowledgeSourceDetail(sourceId: string): Promise<AdminKnowledgeSourceDetailResponse> {
  return request<AdminKnowledgeSourceDetailResponse>(`/admin/knowledge/${encodeURIComponent(sourceId)}`);
}

export function getAdminKnowledgeBases(): Promise<AdminKnowledgeBasesResponse> {
  return request<AdminKnowledgeBasesResponse>("/admin/knowledge-bases");
}

export function createKnowledgeBase(payload: {
  knowledge_base_code: string;
  name: string;
  description: string;
}): Promise<AdminKnowledgeBasesResponse["items"][number]> {
  return request<AdminKnowledgeBasesResponse["items"][number]>("/admin/knowledge-bases", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateKnowledgeBase(
  knowledgeBaseCode: string,
  payload: { name: string; description: string; status: string },
): Promise<AdminKnowledgeBasesResponse["items"][number]> {
  return request<AdminKnowledgeBasesResponse["items"][number]>(`/admin/knowledge-bases/${knowledgeBaseCode}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function deleteKnowledgeBase(knowledgeBaseCode: string): Promise<{ deleted: boolean }> {
  return request<{ deleted: boolean }>(`/admin/knowledge-bases/${knowledgeBaseCode}`, {
    method: "DELETE",
  });
}

export function ingestKnowledgeSource(payload: {
  knowledge_base_code: string;
  name: string;
  content: string;
  source_type: string;
  owner: string;
}): Promise<KnowledgeIngestResponse> {
  return request<KnowledgeIngestResponse>("/admin/knowledge/ingest", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function ingestWikiSource(payload: {
  knowledge_base_code: string;
  name: string;
  content: string;
  source_type: string;
  owner: string;
}): Promise<KnowledgeIngestResponse> {
  return request<KnowledgeIngestResponse>("/admin/wiki/sources/ingest", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function searchAdminWiki(params: {
  query: string;
  topK?: number;
  spaceCode?: string;
}): Promise<AdminWikiSearchResponse> {
  const search = new URLSearchParams();
  search.set("query", params.query);
  if (params.topK) {
    search.set("top_k", String(params.topK));
  }
  if (params.spaceCode) {
    search.set("space_code", params.spaceCode);
  }
  return request<AdminWikiSearchResponse>(`/admin/wiki/search?${search.toString()}`);
}

export function getAdminWikiPages(params?: {
  status?: string;
  pageType?: string;
  spaceCode?: string;
}): Promise<AdminWikiPagesResponse> {
  const search = new URLSearchParams();
  if (params?.status) {
    search.set("status", params.status);
  }
  if (params?.pageType) {
    search.set("page_type", params.pageType);
  }
  if (params?.spaceCode) {
    search.set("space_code", params.spaceCode);
  }
  const suffix = search.size ? `?${search.toString()}` : "";
  return request<AdminWikiPagesResponse>(`/admin/wiki/pages${suffix}`);
}

export function getAdminWikiCompileRuns(): Promise<AdminWikiCompileRunsResponse> {
  return request<AdminWikiCompileRunsResponse>("/admin/wiki/compile-runs");
}

export function getAdminWikiFileDistribution(params?: {
  spaceCode?: string;
  groupBy?: string;
  coverageStatus?: string;
  sourceType?: string;
  owner?: string;
  keyword?: string;
}): Promise<AdminWikiFileDistributionResponse> {
  const search = new URLSearchParams();
  if (params?.spaceCode) {
    search.set("space_code", params.spaceCode);
  }
  if (params?.groupBy) {
    search.set("group_by", params.groupBy);
  }
  if (params?.coverageStatus) {
    search.set("coverage_status", params.coverageStatus);
  }
  if (params?.sourceType) {
    search.set("source_type", params.sourceType);
  }
  if (params?.owner) {
    search.set("owner", params.owner);
  }
  if (params?.keyword) {
    search.set("keyword", params.keyword);
  }
  const suffix = search.size ? `?${search.toString()}` : "";
  return request<AdminWikiFileDistributionResponse>(`/admin/wiki/file-distribution${suffix}`);
}

export function getAdminWikiFileDistributionDetail(
  sourceId: string,
  spaceCode?: string,
): Promise<AdminWikiFileDistributionDetailResponse> {
  const suffix = spaceCode ? `?space_code=${encodeURIComponent(spaceCode)}` : "";
  return request<AdminWikiFileDistributionDetailResponse>(`/admin/wiki/file-distribution/${sourceId}${suffix}`);
}

export function compileAdminWiki(payload?: {
  source_id?: string | null;
  space_code?: string;
}): Promise<WikiCompileResponse> {
  return request<WikiCompileResponse>("/admin/wiki/compile", {
    method: "POST",
    body: JSON.stringify({
      source_id: payload?.source_id ?? null,
      space_code: payload?.space_code ?? "knowledge",
    }),
  });
}

export function getAdminTraces(): Promise<AdminTracesResponse> {
  return request<AdminTracesResponse>("/admin/traces");
}

export function confirmDraftAction(draftId: string): Promise<DraftActionResponse> {
  return request<DraftActionResponse>(`/chat/actions/${draftId}/confirm`, {
    method: "POST",
  });
}

export function getLLMRuntime(tenantId?: string): Promise<LLMRuntimeConfig> {
  const query = tenantId ? `?tenant_id=${encodeURIComponent(tenantId)}` : "";
  return request<LLMRuntimeConfig>(`/admin/llm-runtime${query}`);
}

export function updateLLMRuntime(payload: {
  tenant_id?: string | null;
  provider?: string;
  base_url: string;
  model: string;
  api_key: string;
  temperature: number;
  system_prompt: string;
}): Promise<LLMRuntimeConfig> {
  return request<LLMRuntimeConfig>("/admin/llm-runtime", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

// Tenant CRUD
export function listTenants(): Promise<TenantListResponse> {
  return request<TenantListResponse>("/admin/tenants");
}

export function createTenant(payload: {
  name: string;
  package: string;
  environment: string;
  budget: string;
}): Promise<TenantProfile> {
  return request<TenantProfile>("/admin/tenants", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateTenant(
  tenantId: string,
  payload: {
    name: string;
    package: string;
    environment: string;
    budget: string;
    active: boolean;
  },
): Promise<TenantProfile> {
  return request<TenantProfile>(`/admin/tenants/${tenantId}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function deleteTenant(tenantId: string): Promise<{ deleted: boolean }> {
  return request<{ deleted: boolean }>(`/admin/tenants/${tenantId}`, {
    method: "DELETE",
  });
}

// User CRUD
export function listTenantUsers(tenantId: string): Promise<{ users: UserProfile[] }> {
  return request<{ users: UserProfile[] }>(`/admin/tenants/${tenantId}/users`);
}

export function createUser(
  tenantId: string,
  payload: {
    email: string;
    password: string;
    role: string;
    scopes: string[];
  },
): Promise<UserProfile> {
  return request<UserProfile>(`/admin/tenants/${tenantId}/users`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateUser(
  tenantId: string,
  userId: string,
  payload: {
    role: string;
    scopes: string[];
  },
): Promise<UserProfile> {
  return request<UserProfile>(`/admin/tenants/${tenantId}/users/${userId}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function deleteUser(tenantId: string, userId: string): Promise<{ deleted: boolean }> {
  return request<{ deleted: boolean }>(`/admin/tenants/${tenantId}/users/${userId}`, {
    method: "DELETE",
  });
}

// Auth
export function login(payload: { email: string; password: string }): Promise<AuthResponse> {
  return request<AuthResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function register(payload: {
  email: string;
  password: string;
  tenant_id: string;
  role?: string;
}): Promise<AuthResponse> {
  return request<AuthResponse>("/auth/register", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getCurrentUser(): Promise<AuthResponse["user"]> {
  return request<AuthResponse["user"]>("/auth/me");
}
