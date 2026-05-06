import type {
  AdminKnowledgeResponse,
  AdminKnowledgeSourceAttributesResponse,
  AdminKnowledgeSourceDetailResponse,
  AdminKnowledgeBasesResponse,
  AdminPackagesResponse,
  AdminReleasesResponse,
  AdminSecurityResponse,
  AdminSystemResponse,
  AdminTracesResponse,
  AdminWikiCompileRunsResponse,
  AdminWikiFileDistributionDetailResponse,
  AdminWikiFileDistributionResponse,
  AdminWikiPagesResponse,
  AdminWikiSearchResponse,
  AIActionListResponse,
  AIActionRunResponse,
  AuthResponse,
  BusinessOutput,
  BusinessOutputListResponse,
  BusinessObjectListResponse,
  BusinessObjectLookupResponse,
  ChatCompletionResponse,
  ChatStreamEvent,
  ConversationListResponse,
  ConversationResponse,
  DraftActionResponse,
  HomeSnapshot,
  LLMRuntimeConfig,
  KnowledgeIngestResponse,
  McpServer,
  McpServersResponse,
  PackageBundleUninstallResult,
  PackageDetailResponse,
  PackageImpactResponse,
  PackageKnowledgeImportResult,
  PackageKnowledgePreviewResponse,
  PasswordKeyResponse,
  PluginConfigSchemaResponse,
  PluginCapabilityTestResponse,
  TenantListResponse,
  TenantPackagesResponse,
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

function base64ToArrayBuffer(value: string): ArrayBuffer {
  const binary = window.atob(value);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return bytes.buffer;
}

function arrayBufferToBase64(value: ArrayBuffer): string {
  const bytes = new Uint8Array(value);
  let binary = "";
  for (const byte of bytes) {
    binary += String.fromCharCode(byte);
  }
  return window.btoa(binary);
}

async function importPasswordPublicKey(publicKeyPem: string): Promise<CryptoKey> {
  const publicKeyBody = publicKeyPem
    .replace("-----BEGIN PUBLIC KEY-----", "")
    .replace("-----END PUBLIC KEY-----", "")
    .replace(/\s/g, "");

  return window.crypto.subtle.importKey(
    "spki",
    base64ToArrayBuffer(publicKeyBody),
    {
      name: "RSA-OAEP",
      hash: "SHA-256",
    },
    false,
    ["encrypt"],
  );
}

async function encryptLoginPassword(password: string, publicKeyPem: string): Promise<string> {
  if (typeof window === "undefined" || !window.crypto?.subtle) {
    throw new Error("当前浏览器不支持登录密码加密。");
  }

  const key = await importPasswordPublicKey(publicKeyPem);
  const ciphertext = await window.crypto.subtle.encrypt(
    { name: "RSA-OAEP" },
    key,
    new TextEncoder().encode(password),
  );
  return arrayBufferToBase64(ciphertext);
}

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

function buildAuthHeaders(extra?: Record<string, string>): Record<string, string> {
  const headers: Record<string, string> = {
    ...(extra ?? {}),
  };

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

  return headers;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const requiresBrowserAuth =
    path.startsWith("/admin") ||
    path.startsWith("/ai") ||
    path.startsWith("/outputs") ||
    path.startsWith("/workspace") ||
    path.startsWith("/chat/actions") ||
    path.startsWith("/chat/conversations") ||
    path.startsWith("/chat/traces");
  if (typeof window === "undefined" && requiresBrowserAuth) {
    throw new Error("Authenticated requests require browser context.");
  }

  const target =
    path.startsWith("/admin") ||
    path.startsWith("/ai") ||
    path.startsWith("/outputs") ||
    path.startsWith("/workspace") ||
    path.startsWith("/chat/actions") ||
    path.startsWith("/chat/conversations") ||
    path.startsWith("/chat/traces")
      ? withAuthContext(path)
      : `${API_BASE_URL}${path}`;

  const headers = buildAuthHeaders({
    "Content-Type": "application/json",
    ...(init?.headers as Record<string, string> ?? {}),
  });

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

export function getChatConversations(): Promise<ConversationListResponse> {
  return request<ConversationListResponse>("/chat/conversations");
}

export function createChatConversation(): Promise<ConversationResponse> {
  return request<ConversationResponse>("/chat/conversations", {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export function getChatConversation(conversationId: string): Promise<ConversationResponse> {
  return request<ConversationResponse>(`/chat/conversations/${encodeURIComponent(conversationId)}`);
}

export function deleteChatConversation(conversationId: string): Promise<{ deleted: boolean }> {
  return request<{ deleted: boolean }>(`/chat/conversations/${encodeURIComponent(conversationId)}`, {
    method: "DELETE",
  });
}

export async function streamChatCompletion(
  message: string,
  retrievalMode: "auto" | "rag" | "wiki",
  onEvent: (event: ChatStreamEvent) => void,
  conversationId?: string,
  packageContext?: {
    primary_package?: string;
    common_packages?: string[];
  },
): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/chat/completions/stream`, {
    method: "POST",
    headers: buildAuthHeaders({
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    }),
    body: JSON.stringify({
      message,
      conversation_id: conversationId,
      retrieval_mode: retrievalMode,
      primary_package: packageContext?.primary_package,
      common_packages: packageContext?.common_packages ?? [],
    }),
    cache: "no-store",
  });

  if (!response.ok || !response.body) {
    const detail = await response.text();
    if (response.status === 401) {
      clearStoredAuth();
      redirectToLogin();
      throw new Error(AUTH_EXPIRED_MESSAGE);
    }
    throw new Error(detail || `API request failed: ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() ?? "";

    for (const block of blocks) {
      const dataLine = block.split("\n").find((line) => line.startsWith("data: "));
      if (!dataLine) continue;
      const event = JSON.parse(dataLine.slice(6)) as ChatStreamEvent;
      onEvent(event);
      if (event.event === "error") {
        throw new Error(event.message);
      }
    }
  }
}

export function getTrace(traceId: string): Promise<TraceResponse> {
  return request<TraceResponse>(`/chat/traces/${traceId}`);
}

export function listAIActions(packageId?: string): Promise<AIActionListResponse> {
  const suffix = packageId ? `?package_id=${encodeURIComponent(packageId)}` : "";
  return request<AIActionListResponse>(`/ai/actions${suffix}`);
}

export function runAIAction(
  actionId: string,
  payload: {
    package_id: string;
    source?: "workspace" | "chat" | "embed" | "api" | string;
    object: {
      object_type: string;
      object_id: string;
    };
    inputs?: Record<string, unknown>;
    data_input?: {
      mode: "platform_pull" | "host_context" | "mixed" | string;
      context?: Record<string, unknown>;
    };
  },
): Promise<AIActionRunResponse> {
  return request<AIActionRunResponse>(`/ai/actions/${encodeURIComponent(actionId)}/run`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getAIRunTrace(runId: string): Promise<TraceResponse> {
  return request<TraceResponse>(`/ai/runs/${encodeURIComponent(runId)}/trace`);
}

export function listBusinessObjects(packageId?: string): Promise<BusinessObjectListResponse> {
  const suffix = packageId ? `?package_id=${encodeURIComponent(packageId)}` : "";
  return request<BusinessObjectListResponse>(`/ai/business-objects${suffix}`);
}

export function lookupBusinessObject(payload: {
  package_id: string;
  object_type: string;
  object_id: string;
}): Promise<BusinessObjectLookupResponse> {
  return request<BusinessObjectLookupResponse>("/ai/business-objects/lookup", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getAdminPackages(): Promise<AdminPackagesResponse> {
  return request<AdminPackagesResponse>("/admin/packages");
}

export type PackageImportResult = {
  package_id: string;
  version: string;
  name: string;
  installed_path: string;
  skills: number;
  tools: number;
  plugins: number;
};

export async function importPackageBundle(
  file: File,
  options: { overwrite?: boolean } = {},
): Promise<PackageImportResult> {
  const overwrite = options.overwrite ? "true" : "false";
  const url = withAuthContext(`/admin/packages/import?overwrite=${overwrite}`);
  const formData = new FormData();
  formData.append("file", file);
  const headers = buildAuthHeaders();
  // Let the browser set multipart Content-Type with boundary.
  delete (headers as Record<string, string>)["Content-Type"];
  const response = await fetch(url, {
    method: "POST",
    headers,
    body: formData,
    cache: "no-store",
  });
  if (!response.ok) {
    let detail = "";
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      detail = await response.text();
    }
    throw new Error(detail || `导入失败 (HTTP ${response.status})`);
  }
  return (await response.json()) as PackageImportResult;
}

export function getPackageDetail(packageId: string): Promise<PackageDetailResponse> {
  return request<PackageDetailResponse>(`/admin/packages/${encodeURIComponent(packageId)}`);
}

export function importPackageKnowledge(
  packageId: string,
  options: { autoOnly?: boolean } = {},
): Promise<PackageKnowledgeImportResult> {
  return request<PackageKnowledgeImportResult>("/admin/packages/knowledge/import", {
    method: "POST",
    body: JSON.stringify({
      package_id: packageId,
      auto_only: options.autoOnly ?? false,
    }),
  });
}

export function previewPackageKnowledge(
  packageId: string,
  file: string,
): Promise<PackageKnowledgePreviewResponse> {
  return request<PackageKnowledgePreviewResponse>("/admin/packages/knowledge/preview", {
    method: "POST",
    body: JSON.stringify({
      package_id: packageId,
      file,
    }),
  });
}

export function uninstallPackageBundle(packageId: string): Promise<PackageBundleUninstallResult> {
  return request<PackageBundleUninstallResult>(`/admin/packages/${encodeURIComponent(packageId)}/bundle`, {
    method: "DELETE",
  });
}

export function getPackageImpact(target: string): Promise<PackageImpactResponse> {
  return request<PackageImpactResponse>(`/admin/packages/impact?target=${encodeURIComponent(target)}`);
}

export function getPluginConfigSchema(pluginName: string): Promise<PluginConfigSchemaResponse> {
  return request<PluginConfigSchemaResponse>(`/admin/plugins/${encodeURIComponent(pluginName)}/config-schema`);
}

export function updatePluginConfig(
  pluginName: string,
  config: Record<string, unknown>,
): Promise<{ plugin_name: string; config: Record<string, unknown> }> {
  return request<{ plugin_name: string; config: Record<string, unknown> }>(
    `/admin/plugins/${encodeURIComponent(pluginName)}/config`,
    {
      method: "PUT",
      body: JSON.stringify({ config }),
    },
  );
}

export function testPluginCapability(
  pluginName: string,
  capabilityName: string,
  input: Record<string, unknown>,
): Promise<PluginCapabilityTestResponse> {
  return request<PluginCapabilityTestResponse>(
    `/admin/plugins/${encodeURIComponent(pluginName)}/capabilities/${encodeURIComponent(capabilityName)}/test`,
    {
      method: "POST",
      body: JSON.stringify({ input }),
    },
  );
}

export function listMcpServers(): Promise<McpServersResponse> {
  return request<McpServersResponse>("/admin/mcp-servers");
}

export function upsertMcpServer(payload: {
  name: string;
  transport: "streamable-http" | "http";
  endpoint: string;
  auth_ref?: string;
  headers?: Record<string, string>;
  status?: "active" | "disabled";
}): Promise<McpServer> {
  return request<McpServer>(`/admin/mcp-servers/${encodeURIComponent(payload.name)}`, {
    method: "PUT",
    body: JSON.stringify({
      name: payload.name,
      transport: payload.transport,
      endpoint: payload.endpoint,
      auth_ref: payload.auth_ref ?? "",
      headers: payload.headers ?? {},
      status: payload.status ?? "active",
    }),
  });
}

export function deleteMcpServer(name: string): Promise<{ name: string; deleted: boolean }> {
  return request<{ name: string; deleted: boolean }>(`/admin/mcp-servers/${encodeURIComponent(name)}`, {
    method: "DELETE",
  });
}

export function getTenantPackages(tenantId: string): Promise<TenantPackagesResponse> {
  return request<TenantPackagesResponse>(`/admin/tenants/${encodeURIComponent(tenantId)}/packages`);
}

export function updateTenantPackages(
  tenantId: string,
  payload: {
    primary_package: string;
    common_packages: string[];
  },
): Promise<TenantPackagesResponse> {
  return request<TenantPackagesResponse>(`/admin/tenants/${encodeURIComponent(tenantId)}/packages`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function getAdminSystem(): Promise<AdminSystemResponse> {
  return request<AdminSystemResponse>("/admin/system");
}

export function getAdminReleases(): Promise<AdminReleasesResponse> {
  return request<AdminReleasesResponse>("/admin/releases");
}

export function updateReleasePlan(
  releaseId: string,
  payload: { status: string; rollout_percent: number },
): Promise<AdminReleasesResponse["releases"][number]> {
  return request<AdminReleasesResponse["releases"][number]>(`/admin/releases/${encodeURIComponent(releaseId)}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function getAdminSecurity(): Promise<AdminSecurityResponse> {
  return request<AdminSecurityResponse>("/admin/security");
}

export function updateToolOverride(payload: {
  tenant_id: string;
  tool_name: string;
  quota?: number | null;
  timeout?: number | null;
  disabled: boolean;
}): Promise<NonNullable<AdminSecurityResponse["tool_overrides"]>[number]> {
  return request<NonNullable<AdminSecurityResponse["tool_overrides"]>[number]>("/admin/security/tool-overrides", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function updateOutputGuardRule(payload: {
  rule_id: string;
  package_id: string;
  pattern: string;
  action: string;
  source: string;
  enabled: boolean;
}): Promise<NonNullable<AdminSecurityResponse["redlines"]>[number]> {
  return request<NonNullable<AdminSecurityResponse["redlines"]>[number]>("/admin/security/redlines", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function getAdminKnowledge(knowledgeBaseCode?: string): Promise<AdminKnowledgeResponse> {
  const suffix = knowledgeBaseCode ? `?knowledge_base_code=${encodeURIComponent(knowledgeBaseCode)}` : "";
  return request<AdminKnowledgeResponse>(`/admin/knowledge${suffix}`);
}

export function getAdminKnowledgeSourceDetail(sourceId: string): Promise<AdminKnowledgeSourceDetailResponse> {
  return request<AdminKnowledgeSourceDetailResponse>(`/admin/knowledge/${encodeURIComponent(sourceId)}`);
}

export function getAdminKnowledgeSourceAttributes(sourceId: string): Promise<AdminKnowledgeSourceAttributesResponse> {
  return request<AdminKnowledgeSourceAttributesResponse>(
    `/admin/knowledge/sources/${encodeURIComponent(sourceId)}/attributes`,
  );
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
  return request<AdminKnowledgeBasesResponse["items"][number]>(`/admin/knowledge-bases/${encodeURIComponent(knowledgeBaseCode)}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function deleteKnowledgeBase(knowledgeBaseCode: string): Promise<{ deleted: boolean }> {
  return request<{ deleted: boolean }>(`/admin/knowledge-bases/${encodeURIComponent(knowledgeBaseCode)}`, {
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

export function getAdminWikiSourceDetail(sourceId: string): Promise<AdminKnowledgeSourceDetailResponse> {
  return request<AdminKnowledgeSourceDetailResponse>(`/admin/wiki/sources/${encodeURIComponent(sourceId)}`);
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
  embedding_provider?: string | null;
  embedding_base_url?: string | null;
  embedding_model?: string | null;
  embedding_api_key?: string | null;
  embedding_dimensions?: number | null;
  embedding_enabled?: boolean | null;
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
export async function getPasswordKey(): Promise<PasswordKeyResponse> {
  return request<PasswordKeyResponse>("/auth/password-key");
}

export async function login(payload: { email: string; password: string }): Promise<AuthResponse> {
  const passwordKey = await getPasswordKey();
  if (passwordKey.algorithm !== "RSA-OAEP-SHA256") {
    throw new Error("登录密码加密算法不受支持。");
  }
  const encryptedPassword = await encryptLoginPassword(payload.password, passwordKey.public_key);

  return request<AuthResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify({
      email: payload.email,
      encrypted_password: encryptedPassword,
      key_id: passwordKey.key_id,
    }),
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

export function listBusinessOutputs(filters?: {
  type?: string;
  package?: string;
  status?: string;
}): Promise<BusinessOutputListResponse> {
  const params = new URLSearchParams();
  if (filters?.type) params.set("type", filters.type);
  if (filters?.package) params.set("package", filters.package);
  if (filters?.status) params.set("status", filters.status);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return request<BusinessOutputListResponse>(`/outputs${suffix}`);
}

export function getBusinessOutput(outputId: string): Promise<BusinessOutput> {
  return request<BusinessOutput>(`/outputs/${encodeURIComponent(outputId)}`);
}

export function createBusinessOutput(payload: {
  type: string;
  title: string;
  package_id: string;
  payload?: Record<string, unknown>;
  citations?: string[];
  conversation_id?: string | null;
  trace_id?: string | null;
  summary?: string;
}): Promise<BusinessOutput> {
  return request<BusinessOutput>("/outputs", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateBusinessOutput(
  outputId: string,
  payload: Partial<{
    title: string;
    status: string;
    payload: Record<string, unknown>;
    citations: string[];
    summary: string;
    linked_draft_group_id: string | null;
  }>,
): Promise<BusinessOutput> {
  return request<BusinessOutput>(`/outputs/${encodeURIComponent(outputId)}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}
