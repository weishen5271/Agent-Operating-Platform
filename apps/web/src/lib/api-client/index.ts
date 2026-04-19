import type {
  AdminKnowledgeResponse,
  AdminPackagesResponse,
  AdminSecurityResponse,
  AdminSystemResponse,
  AdminTracesResponse,
  AuthResponse,
  ChatCompletionResponse,
  DraftActionResponse,
  HomeSnapshot,
  LLMRuntimeConfig,
  TenantProfile,
  TraceResponse,
  UserProfile,
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

function getAuthUserContext(): AuthUserContext | null {
  if (typeof window === "undefined") {
    return null;
  }

  const rawUser = localStorage.getItem("auth_user");
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
  const target = path.startsWith("/admin") || path.startsWith("/workspace") || path.startsWith("/chat/actions")
    ? withAuthContext(path)
    : `${API_BASE_URL}${path}`;

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init?.headers as Record<string, string> ?? {}),
  };

  // Add auth token if available
  if (typeof window !== "undefined") {
    const token = localStorage.getItem("auth_token");
    if (token) {
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
): Promise<ChatCompletionResponse> {
  return request<ChatCompletionResponse>("/chat/completions", {
    method: "POST",
    body: JSON.stringify({
      message,
      conversation_id: conversationId,
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

export function getAdminKnowledge(): Promise<AdminKnowledgeResponse> {
  return request<AdminKnowledgeResponse>("/admin/knowledge");
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
export function createTenant(payload: {
  tenant_id: string;
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
    user_id: string;
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
