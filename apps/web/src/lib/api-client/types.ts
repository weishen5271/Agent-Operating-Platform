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
    page_id?: string | null;
    revision_id?: string | null;
    citation_id?: string | null;
    claim_text?: string | null;
    source_id?: string | null;
    chunk_id?: string | null;
    locator?: string | null;
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
  warnings?: string[];
};

export type ConversationListResponse = {
  items: Array<{
    conversation_id: string;
    title: string;
    updated_at: string;
  }>;
};

export type ConversationResponse = {
  conversation_id: string;
  title: string;
  updated_at: string;
  messages: Array<{
    role: "user" | "assistant";
    content: string;
    created_at: string;
  }>;
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

export type ChatStreamEvent =
  | {
      event: "trace_step";
      trace_id: string;
      step: TraceResponse["steps"][number];
    }
  | {
      event: "response_meta";
      trace_id: string;
      conversation_id: string;
      intent: string;
      strategy: string;
      sources: ChatCompletionResponse["sources"];
      warnings?: string[];
      draft_action?: ChatCompletionResponse["draft_action"];
    }
  | {
      event: "message_delta";
      content: string;
    }
  | {
      event: "message_done";
      content: string;
    }
  | {
      event: "done";
    }
  | {
      event: "error";
      message: string;
      status?: number;
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

export type AdminKnowledgeSourceDetailResponse = {
  source: {
    source_id: string;
    tenant_id: string;
    knowledge_base_code: string;
    name: string;
    source_type: string;
    owner: string;
    chunk_count: number;
    status: string;
  };
  chunks: Array<{
    chunk_id: string;
    source_id: string;
    tenant_id: string;
    chunk_index: number;
    title: string;
    content: string;
    content_hash: string;
    metadata_json: Record<string, unknown>;
    token_count: number;
    status: string;
    created_at: string;
  }>;
  content: string;
};

export type LLMRuntimeConfig = {
  provider: string;
  base_url: string;
  model: string;
  api_key_configured: boolean;
  temperature: number;
  system_prompt: string;
  enabled: boolean;
  embedding_provider?: string;
  embedding_base_url?: string;
  embedding_model?: string;
  embedding_dimensions?: number;
  embedding_api_key_configured?: boolean;
  embedding_enabled?: boolean;
};

export type TenantProfile = {
  tenant_id: string;
  name: string;
  package: string;
  environment: string;
  budget: string;
  active: boolean;
};

export type TenantListResponse = {
  tenants: TenantProfile[];
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
    knowledge_base_code: string;
    name: string;
    source_type: string;
    owner: string;
    chunk_count: number;
    status: string;
  }>;
};

export type AdminKnowledgeBasesResponse = {
  items: Array<{
    knowledge_base_id: string;
    knowledge_base_code: string;
    tenant_id: string;
    name: string;
    description: string;
    status: string;
    created_by: string;
    updated_by: string;
    created_at: string;
    updated_at: string;
  }>;
};

export type KnowledgeSource = AdminKnowledgeResponse["sources"][number];

export type KnowledgeIngestResponse = {
  source: KnowledgeSource;
};

export type AdminWikiSearchResponse = {
  summary: string;
  hits: Array<{
    page_id: string;
    revision_id?: string | null;
    revision_no: number;
    title: string;
    summary: string;
    snippet: string;
    citation_id?: string | null;
    claim_text: string;
    evidence_snippet: string;
    source_id?: string | null;
    chunk_id?: string | null;
    score: number;
    locator: string;
  }>;
  retrieval: {
    backend: string;
    query: string;
    matched: boolean;
    candidate_count: number;
    match_count: number;
  };
};

export type AdminWikiPagesResponse = {
  pages: Array<{
    page_id: string;
    tenant_id: string;
    space_code: string;
    page_type: string;
    title: string;
    slug: string;
    summary: string;
    content_markdown: string;
    metadata_json: Record<string, unknown>;
    status: string;
    confidence: string;
    freshness_score: number;
    source_count: number;
    citation_count: number;
    revision_no: number;
    created_by: string;
    updated_by: string;
    created_at: string;
    updated_at: string;
  }>;
};

export type AdminWikiCompileRunsResponse = {
  items: Array<{
    compile_run_id: string;
    tenant_id: string;
    trigger_type: string;
    status: string;
    scope_type: string;
    scope_value: string;
    input_source_ids: string[];
    input_chunk_ids: string[];
    affected_page_ids: string[];
    summary: string;
    error_message: string;
    token_usage: number;
    started_at?: string | null;
    finished_at?: string | null;
    created_by: string;
    created_at: string;
  }>;
};

export type AdminWikiFileDistributionResponse = {
  overview: {
    total_sources: number;
    compiled_sources: number;
    uncovered_sources: number;
    high_impact_sources: number;
    total_pages: number;
    total_citations: number;
    avg_pages_per_source: number;
    avg_sources_per_page: number;
    latest_compile_run_id?: string | null;
    latest_compile_finished_at?: string | null;
  };
  groups: Array<{
    group_key: string;
    group_label: string;
    source_count: number;
    compiled_count: number;
    uncovered_count: number;
    citation_count: number;
    page_count: number;
    dominant_status: string;
  }>;
  items: Array<{
    source_id: string;
    tenant_id: string;
    source_name: string;
    source_type: string;
    owner: string;
    group_path: string;
    chunk_count: number;
    status: string;
    coverage_status: string;
    compiled: boolean;
    page_count: number;
    citation_count: number;
    distribution_score: number;
    hotspot_score: number;
    latest_compile_run_id?: string | null;
    latest_compile_finished_at?: string | null;
  }>;
};

export type AdminWikiFileDistributionDetailResponse = {
  item: AdminWikiFileDistributionResponse["items"][number];
  related_pages: Array<{
    page_id: string;
    title: string;
    slug: string;
    citation_count: number;
    contribution_score: number;
  }>;
  diagnostic_tags: string[];
};

export type WikiCompileResponse = {
  compile_run: AdminWikiCompileRunsResponse["items"][number];
  pages: Array<{
    page: AdminWikiPagesResponse["pages"][number];
    revision: {
      revision_id: string;
      page_id: string;
      tenant_id: string;
      revision_no: number;
      compile_run_id?: string | null;
      change_type: string;
      content_markdown: string;
      summary: string;
      change_summary: string;
      quality_score: number;
      metadata_json: Record<string, unknown>;
      created_at: string;
      created_by: string;
    };
    citations: Array<{
      citation_id: string;
      tenant_id: string;
      page_id: string;
      revision_id: string;
      section_key: string;
      claim_text: string;
      source_id: string;
      chunk_id: string;
      evidence_snippet: string;
      support_type: string;
      created_at: string;
    }>;
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
