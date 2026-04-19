export type HomeSnapshot = {
  tenant: {
    id: string;
    name: string;
    package: string;
  };
  llm_runtime?: LLMRuntimeConfig;
  enabled_capabilities: Array<{
    name: string;
    description: string;
    risk_level: string;
    required_scope: string;
  }>;
  recent_conversations: Array<{
    conversation_id: string;
    title: string;
    updated_at: string;
  }>;
};

export type ChatCompletionResponse = {
  trace_id: string;
  conversation_id: string;
  intent: string;
  strategy: string;
  message: {
    role: string;
    content: string;
  };
  sources: Array<{
    id: string;
    title: string;
    snippet: string;
    source_type: string;
  }>;
  draft_action?: {
    draft_id: string;
    title: string;
    capability_name: string;
    risk_level: string;
    status: string;
    summary: string;
    approval_hint: string;
    payload: Record<string, unknown>;
    created_at: string;
  } | null;
};

export type TraceResponse = {
  trace_id: string;
  tenant_id: string;
  user_id: string;
  message: string;
  intent: string;
  strategy: string;
  answer: string;
  created_at: string;
  steps: Array<{
    name: string;
    status: string;
    summary: string;
    timestamp: string;
  }>;
  sources: ChatCompletionResponse["sources"];
};

export type AdminPackagesResponse = {
  packages: Array<{
    name: string;
    version: string;
    owner: string;
    status: string;
  }>;
  capabilities: Array<{
    name: string;
    risk_level: string;
    side_effect_level: string;
    required_scope: string;
  }>;
};

export type AdminSystemResponse = {
  tenants: Array<{
    tenant_id: string;
    name: string;
    package: string;
    environment: string;
    budget: string;
    active: boolean;
  }>;
  roles: Array<{
    name: string;
    scope_count: number;
    member_count: number;
  }>;
  llm_runtime?: LLMRuntimeConfig;
};

export type AdminSecurityResponse = {
  events: Array<{
    event_id: string;
    tenant_id: string;
    category: string;
    severity: string;
    title: string;
    status: string;
    owner: string;
  }>;
  drafts: Array<{
    draft_id: string;
    title: string;
    capability_name: string;
    risk_level: string;
    status: string;
    summary: string;
    approval_hint: string;
    payload: Record<string, unknown>;
    created_at: string;
  }>;
};

export type DraftActionResponse = {
  draft_id: string;
  title: string;
  capability_name: string;
  risk_level: string;
  status: string;
  summary: string;
  approval_hint: string;
  payload: Record<string, unknown>;
  created_at: string;
};

export type LLMRuntimeConfig = {
  provider: string;
  base_url: string;
  model: string;
  api_key_configured: boolean;
  temperature: number;
  system_prompt: string;
  enabled: boolean;
};

export type TenantProfile = {
  tenant_id: string;
  name: string;
  package: string;
  environment: string;
  budget: string;
  active: boolean;
};

export type UserProfile = {
  user_id: string;
  tenant_id: string;
  role: string;
  scopes: string[];
  email?: string;
};

export type LoginRequest = {
  email: string;
  password: string;
};

export type RegisterRequest = {
  email: string;
  password: string;
  tenant_id: string;
  role?: string;
};

export type AuthResponse = {
  access_token: string;
  token_type: string;
  user: {
    user_id: string;
    tenant_id: string;
    role: string;
    email: string;
    tenant_name: string;
  };
};

export type AdminKnowledgeResponse = {
  sources: Array<{
    source_id: string;
    tenant_id: string;
    name: string;
    source_type: string;
    owner: string;
    chunk_count: number;
    status: string;
  }>;
};

export type AdminTracesResponse = {
  items: Array<{
    trace_id: string;
    user_id: string;
    intent: string;
    strategy: string;
    message: string;
    answer: string;
    created_at: string;
  }>;
};
