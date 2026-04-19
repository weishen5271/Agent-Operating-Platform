"use client";

import { useCallback, useEffect, useState, useTransition } from "react";

import { getLLMRuntime, updateLLMRuntime } from "@/lib/api-client";
import type { LLMRuntimeConfig } from "@/lib/api-client/types";

type LLMRuntimeFormProps = {
  tenantId?: string;
  initialConfig?: LLMRuntimeConfig;
};

const PROVIDER_HINTS: Record<string, { baseUrl: string; model: string; apiKey: string }> = {
  "openai-compatible": {
    baseUrl: "https://api.openai.com/v1",
    model: "gpt-4o-mini",
    apiKey: "sk-...（仅在需要更新时填写）",
  },
  azure: {
    baseUrl: "https://{resource}.openai.azure.com?api-version=2024-02-15-preview",
    model: "Azure deployment name",
    apiKey: "Azure OpenAI key（仅在需要更新时填写）",
  },
  anthropic: {
    baseUrl: "https://api.anthropic.com",
    model: "claude-3-5-sonnet-latest",
    apiKey: "Anthropic API key（仅在需要更新时填写）",
  },
};

export function LLMRuntimeForm({ tenantId, initialConfig }: LLMRuntimeFormProps) {
  const [baseUrl, setBaseUrl] = useState(initialConfig?.base_url ?? "");
  const [model, setModel] = useState(initialConfig?.model ?? "");
  const [apiKey, setApiKey] = useState("");
  const [provider, setProvider] = useState(initialConfig?.provider ?? "openai-compatible");
  const [temperature, setTemperature] = useState(String(initialConfig?.temperature ?? 0.2));
  const [systemPrompt, setSystemPrompt] = useState(
    initialConfig?.system_prompt ?? "你是企业级 Agent 平台中的智能助手，回答要准确、结构清晰，并优先引用已知上下文。",
  );
  const [runtime, setRuntime] = useState<LLMRuntimeConfig | undefined>(initialConfig);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();
  const providerHints = PROVIDER_HINTS[provider] ?? PROVIDER_HINTS["openai-compatible"];

  const applyConfig = useCallback((config: LLMRuntimeConfig) => {
    setBaseUrl(config.base_url);
    setModel(config.model);
    setProvider(config.provider);
    setTemperature(String(config.temperature));
    setSystemPrompt(config.system_prompt);
    setRuntime(config);
    setApiKey("");
  }, []);

  useEffect(() => {
    let ignore = false;

    if (initialConfig) {
      applyConfig(initialConfig);
      return () => {
        ignore = true;
      };
    }

    setFeedback(null);
    getLLMRuntime(tenantId)
      .then((config) => {
        if (!ignore) {
          applyConfig(config);
        }
      })
      .catch(() => {
        if (!ignore) {
          setFeedback("模型配置加载失败，请确认后端 API 已启动。");
        }
      });

    return () => {
      ignore = true;
    };
  }, [tenantId, initialConfig, applyConfig]);

  async function handleSubmit() {
    setFeedback(null);
    startTransition(async () => {
      try {
        const next = await updateLLMRuntime({
          tenant_id: tenantId,
          provider,
          base_url: baseUrl,
          model,
          api_key: apiKey,
          temperature: Number(temperature),
          system_prompt: systemPrompt,
        });
        setRuntime(next);
        setApiKey("");
        setFeedback(
          next.enabled
            ? "模型配置已生效，统一对话中的知识问答将优先走真实 LLM。"
            : "配置已保存，但当前尚未满足启用条件。",
        );
      } catch {
        setFeedback("模型配置更新失败，请确认后端 API 已启动。");
      }
    });
  }

  return (
    <div className="form-section">
      <div className="form-grid">
        <div className="form-field">
          <label>Provider</label>
          <select value={provider} onChange={(e) => setProvider(e.target.value)}>
            <option value="openai-compatible">OpenAI Compatible</option>
            <option value="azure">Azure OpenAI</option>
            <option value="anthropic">Anthropic</option>
          </select>
        </div>
        <div className="form-field">
          <label>Base URL</label>
          <input
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            placeholder={providerHints.baseUrl}
          />
        </div>
        <div className="form-field">
          <label>Model</label>
          <input
            value={model}
            onChange={(e) => setModel(e.target.value)}
            placeholder={providerHints.model}
          />
        </div>
        <div className="form-field">
          <label>API Key</label>
          <input
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder={providerHints.apiKey}
          />
        </div>
        <div className="form-field">
          <label>Temperature</label>
          <input
            type="number"
            step="0.1"
            min="0"
            max="2"
            value={temperature}
            onChange={(e) => setTemperature(e.target.value)}
          />
        </div>
      </div>

      <div className="form-field form-field-full">
        <label>System Prompt</label>
        <textarea
          value={systemPrompt}
          onChange={(e) => setSystemPrompt(e.target.value)}
          rows={4}
        />
      </div>

      <div className="runtime-meta">
        <span>Provider: {runtime?.provider ?? provider}</span>
        <span>已配置 Key: {runtime?.api_key_configured ? "是" : "否"}</span>
        <span>当前模型: {runtime?.model || model || "未设置"}</span>
        <span className={`status-chip ${runtime?.enabled ? "success" : ""}`}>
          {runtime?.enabled ? "已启用" : "未启用"}
        </span>
      </div>

      <div className="form-actions">
        <button type="button" className="primary-button" disabled={isPending} onClick={handleSubmit}>
          {isPending ? "保存中..." : "保存配置"}
        </button>
      </div>

      {feedback ? <p className="inline-feedback">{feedback}</p> : null}
    </div>
  );
}
