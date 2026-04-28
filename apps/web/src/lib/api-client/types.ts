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

export type TraceNodeType = "capability" | "tool" | "skill" | "retrieval" | "guard" | "runtime";
export type TraceNodeSource = "package" | "_platform" | "_common";

export type RoutingDecision = {
  matched_package_id: string;
  confidence: number;
  candidates: Array<{ package_id: string; confidence: number }>;
  signals: string[];
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
  routing?: RoutingDecision | null;
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
    node_type?: TraceNodeType | null;
    ref?: string | null;
    ref_source?: TraceNodeSource | null;
    ref_version?: string | null;
    duration_ms?: number | null;
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
      routing?: RoutingDecision | null;
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

export type PackageDependency = {
  kind: "platform_skill" | "common_package" | "plugin" | "platform_tool";
  name: string;
  version_range: string;
  current_version: string;
  compatible: boolean;
};

export type SkillSummary = {
  name: string;
  description: string;
  version: string;
  source: TraceNodeSource;
  package_id?: string | null;
  depends_on_capabilities: string[];
  depends_on_tools: string[];
  steps?: Array<Record<string, unknown>>;
  outputs_mapping?: Record<string, unknown>;
};

export type ToolSummary = {
  name: string;
  description: string;
  version: string;
  source: TraceNodeSource;
  timeout_ms: number;
  quota_per_minute: number;
};

export type PackagePluginSummary = {
  name: string;
  description?: string;
  version?: string;
  executor?: string;
  config_schema?: Record<string, PluginConfigFieldSchema>;
  capabilities?: Array<{
    name: string;
    description?: string;
    risk_level?: string;
    side_effect_level?: string;
    required_scope?: string;
  }>;
};

export type AdminPackagesResponse = {
  packages: Array<{
    package_id?: string;
    name: string;
    version: string;
    owner: string;
    domain?: "industry" | "common" | "platform";
    dependencies?: PackageDependency[];
    knowledge_imports?: KnowledgeImportDeclaration[];
    plugins?: PackagePluginSummary[];
  }>;
  capabilities: Array<{
    name: string;
    risk_level: string;
    side_effect_level: string;
    required_scope: string;
    source?: string;
    package_id?: string | null;
  }>;
  skills?: SkillSummary[];
  tools?: ToolSummary[];
};

export type PackageDetailResponse = {
  package_id: string;
  name: string;
  version: string;
  owner: string;
  domain: "industry" | "common" | "platform";
  dependencies: PackageDependency[];
  dependency_summary: {
    platform_skills: number;
    common_packages: number;
    plugins: number;
    tools: number;
  };
  plugins?: PackagePluginSummary[];
  knowledge_imports?: KnowledgeImportDeclaration[];
  source_kind?: "catalog" | "bundle";
  bundle_path?: string | null;
};

export type KnowledgeImportDeclaration = {
  file: string;
  name: string;
  source_type: string;
  knowledge_base_code: string;
  owner: string;
  auto_import: boolean;
  attributes: Record<string, unknown>;
};

export type PackageKnowledgePreviewResponse = KnowledgeImportDeclaration & {
  package_id: string;
  content: string;
};

export type PackageKnowledgeImportResult = {
  package_id: string;
  imported_count: number;
  skipped_count: number;
  imported: Array<{
    file: string;
    source: KnowledgeSource;
  }>;
  skipped: Array<{
    file: string;
    reason: string;
  }>;
};

export type PackageBundleUninstallResult = {
  package_id: string;
  removed: boolean;
};

export type PackageImpactResponse = {
  target: {
    name: string;
    version: string;
  };
  affected_packages: Array<{
    package_id: string;
    name: string;
    version: string;
    dependency: PackageDependency;
    risk: "low" | "medium" | "high";
    compatible: boolean;
    reason: string;
  }>;
};

export type ReleasePlan = {
  release_id: string;
  package_id: string;
  package_name: string;
  skill: string;
  version: string;
  status: string;
  rollout_percent: number;
  metric_delta: string;
  started_at: string;
};

export type AdminReleasesResponse = {
  releases: ReleasePlan[];
};

export type PluginConfigSchemaResponse = {
  plugin_name: string;
  capability: {
    name: string;
    description: string;
    risk_level: string;
    side_effect_level: string;
    required_scope: string;
  };
  config_schema: {
    type: "object";
    properties: Record<string, PluginConfigFieldSchema>;
    required?: string[];
    additionalProperties?: boolean;
  };
  config: Record<string, unknown>;
  auth_refs: string[];
};

export type PluginConfigFieldSchema = {
  type?: string;
  format?: string;
  default?: unknown;
  items?: { type?: string };
  label?: string;
  description?: string;
  properties?: Record<string, PluginConfigFieldSchema>;
  required?: string[];
  additionalProperties?: boolean;
};

export type TenantPackageOption = {
  package_id: string;
  name: string;
  domain: "industry" | "common" | "platform";
  version?: string;
  status?: string;
};

export type TenantPackagesResponse = {
  primary_package: string;
  common_packages: string[];
  available_packages: TenantPackageOption[];
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

export type McpServer = {
  server_id: string;
  name: string;
  transport: "streamable-http" | "http";
  endpoint: string;
  auth_ref: string;
  headers: Record<string, string>;
  status: "active" | "disabled";
};

export type McpServersResponse = {
  servers: McpServer[];
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
  tool_overrides?: Array<{
    tool_name: string;
    tenant_id: string;
    quota?: number;
    timeout?: number;
    disabled?: boolean;
    overridden?: boolean;
    default_quota?: number;
    default_timeout?: number;
  }>;
  redlines?: Array<{
    rule_id: string;
    package_id?: string;
    pattern: string;
    action: string;
    source: string;
    enabled?: boolean;
    recent_triggers: number;
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
    chunk_attributes_schema?: Record<string, {
      type: string;
      indexed: "hot" | "warm" | "cold";
      filter?: string;
    }>;
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

export type AdminKnowledgeSourceAttributesResponse = {
  source_id: string;
  schema: Record<string, {
    type: string;
    indexed: "hot" | "warm" | "cold";
    filter?: string;
  }>;
  fields: Array<{
    field: string;
    type: string;
    indexed: "hot" | "warm" | "cold";
    filter: string;
    hit_count: number;
    chunk_count: number;
    hit_rate: number;
  }>;
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
  enabled_common_packages?: string[];
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
  encrypted_password: string;
  key_id: string;
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

export type PasswordKeyResponse = {
  key_id: string;
  algorithm: "RSA-OAEP-SHA256";
  public_key: string;
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

export type BusinessOutputType = "report" | "chart" | "recommendation" | "action_plan";
export type BusinessOutputStatus = "draft" | "reviewing" | "approved" | "exported" | "archived";

export type BusinessOutput = {
  output_id: string;
  tenant_id: string;
  package_id: string;
  type: BusinessOutputType;
  title: string;
  status: BusinessOutputStatus;
  payload: Record<string, unknown>;
  citations: string[];
  conversation_id: string | null;
  trace_id: string | null;
  linked_draft_group_id: string | null;
  summary: string;
  created_by: string;
  created_at: string | null;
  updated_at: string | null;
};

export type BusinessOutputListResponse = {
  items: BusinessOutput[];
};
