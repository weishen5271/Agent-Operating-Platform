"use client";

import { useEffect, useMemo, useState } from "react";

import { getPluginConfigSchema, listMcpServers, testPluginCapability, updatePluginConfig } from "@/lib/api-client";
import type { McpServer, PackagePluginSummary, PluginConfigFieldSchema, PluginConfigSchemaResponse } from "@/lib/api-client/types";

type FormState = Record<string, unknown>;

const SENSITIVE_FIELD_PATTERN = /(api[_-]?key|secret|password|passwd|token|credential)/i;

function isSensitiveFieldName(field: string): boolean {
  return SENSITIVE_FIELD_PATTERN.test(field);
}

function initialState(schema: PluginConfigSchemaResponse): FormState {
  const state: FormState = { ...schema.config };
  for (const [field, config] of Object.entries(schema.config_schema.properties)) {
    if (state[field] === undefined && config.default !== undefined) {
      state[field] = config.default;
    }
  }
  return state;
}

function isRequired(schema: PluginConfigSchemaResponse, field: string): boolean {
  return schema.config_schema.required?.includes(field) ?? false;
}

function isNestedRequired(schema: PluginConfigFieldSchema, field: string): boolean {
  return schema.required?.includes(field) ?? false;
}

function objectValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function fieldLabel(field: string, config: PluginConfigFieldSchema, parent?: string): string {
  return config.label ?? (parent ? `${parent}.${field}` : field);
}

type CapabilitySummary = NonNullable<PackagePluginSummary["capabilities"]>[number];

function buildInputTemplate(capability: CapabilitySummary | undefined): string {
  const required = capability?.input_schema?.required ?? [];
  const payload = Object.fromEntries(required.map((field) => [field, ""]));
  return JSON.stringify(payload, null, 2);
}

function findSimulatedNotice(value: unknown): string {
  if (!value || typeof value !== "object") return "";
  if (Array.isArray(value)) {
    for (const item of value) {
      const notice = findSimulatedNotice(item);
      if (notice) return notice;
    }
    return "";
  }
  const record = value as Record<string, unknown>;
  if (record.simulated === true) {
    return typeof record.notice === "string" && record.notice ? record.notice : "当前返回标记为模拟/占位数据。";
  }
  for (const item of Object.values(record)) {
    const notice = findSimulatedNotice(item);
    if (notice) return notice;
  }
  return "";
}

export function PluginConfigForm({
  pluginName,
  capabilities = [],
}: {
  pluginName: string;
  capabilities?: CapabilitySummary[];
}) {
  const [schema, setSchema] = useState<PluginConfigSchemaResponse | null>(null);
  const [form, setForm] = useState<FormState>({});
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [mcpServers, setMcpServers] = useState<McpServer[]>([]);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const readCapabilities = useMemo(
    () => capabilities.filter((capability) => capability.side_effect_level === "read"),
    [capabilities],
  );
  const [selectedCapabilityName, setSelectedCapabilityName] = useState(readCapabilities[0]?.name ?? "");
  const selectedCapability = readCapabilities.find((capability) => capability.name === selectedCapabilityName);
  const [testInput, setTestInput] = useState(buildInputTemplate(selectedCapability));
  const [testResult, setTestResult] = useState("");
  const [testSimulatedNotice, setTestSimulatedNotice] = useState("");
  const [testError, setTestError] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    getPluginConfigSchema(pluginName)
      .then((response) => {
        if (!cancelled) {
          setSchema(response);
          setForm(initialState(response));
        }
      })
      .catch((exc) => {
        if (!cancelled) setError(exc instanceof Error ? exc.message : "插件配置加载失败");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [pluginName]);

  useEffect(() => {
    if (!schema?.config_schema.properties.mcp_server) return;
    let cancelled = false;
    listMcpServers()
      .then((response) => {
        if (!cancelled) setMcpServers(response.servers.filter((server) => server.status === "active"));
      })
      .catch(() => {
        if (!cancelled) setMcpServers([]);
      });
    return () => {
      cancelled = true;
    };
  }, [schema]);

  useEffect(() => {
    const firstCapability = readCapabilities[0]?.name ?? "";
    setSelectedCapabilityName((current) =>
      current && readCapabilities.some((capability) => capability.name === current) ? current : firstCapability,
    );
  }, [pluginName, readCapabilities]);

  useEffect(() => {
    setTestInput(buildInputTemplate(selectedCapability));
    setTestResult("");
    setTestSimulatedNotice("");
    setTestError("");
  }, [selectedCapabilityName]);

  function setField(field: string, value: unknown) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  function setNestedField(field: string, nestedField: string, value: unknown) {
    setForm((current) => ({
      ...current,
      [field]: {
        ...objectValue(current[field]),
        [nestedField]: value,
      },
    }));
  }

  async function save() {
    setSaving(true);
    setError("");
    setMessage("");
    try {
      const response = await updatePluginConfig(pluginName, form);
      setForm(response.config);
      setMessage("配置已保存");
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "保存失败");
    } finally {
      setSaving(false);
    }
  }

  async function runCapabilityTest() {
    if (!selectedCapabilityName) return;
    setTesting(true);
    setTestError("");
    setTestResult("");
    setTestSimulatedNotice("");
    try {
      const parsed = JSON.parse(testInput || "{}") as unknown;
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
        throw new Error("测试输入必须是 JSON 对象。");
      }
      const response = await testPluginCapability(pluginName, selectedCapabilityName, parsed as Record<string, unknown>);
      setTestResult(JSON.stringify(response.result, null, 2));
      setTestSimulatedNotice(findSimulatedNotice(response.result));
    } catch (exc) {
      setTestError(exc instanceof Error ? exc.message : "测试失败");
    } finally {
      setTesting(false);
    }
  }

  if (loading) {
    return (
      <div className="empty-state">
        <strong>加载中</strong>
        <p>正在读取插件配置 schema。</p>
      </div>
    );
  }

  if (error && !schema) {
    return (
      <div className="empty-state">
        <strong>加载失败</strong>
        <p>{error}</p>
      </div>
    );
  }

  if (!schema) return null;

  return (
    <div className="plugin-config-form">
      <div className="section-mini-head">
        <h4>{schema.plugin_name}</h4>
        <span className="status-chip plain">{schema.capability.side_effect_level}</span>
      </div>
      {Object.entries(schema.config_schema.properties).map(([field, config]) => {
        const required = isRequired(schema, field);
        const value = form[field];
        const sensitive = isSensitiveFieldName(field);
        const isSecretRef = config.format === "secret-ref" || sensitive;
        const schemaMisconfigured = sensitive && config.format !== "secret-ref";

        if (config.type === "object") {
          const nestedProperties = config.properties ?? {};
          const nestedValue = objectValue(value);
          return (
            <div key={field} className="plugin-config-field">
              <span>
                {fieldLabel(field, config)}
                {required ? <strong> *</strong> : null}
              </span>
              {Object.entries(nestedProperties).map(([nestedField, nestedConfig]) => {
                const nestedRequired = isNestedRequired(config, nestedField);
                const nestedCurrent = nestedValue[nestedField];
                const nestedSensitive = field === "secrets" || nestedConfig.format === "secret-ref" || isSensitiveFieldName(nestedField);
                return (
                  <label key={`${field}.${nestedField}`} className="plugin-config-field nested">
                    <span>
                      {fieldLabel(nestedField, nestedConfig, field)}
                      {nestedRequired ? <strong> *</strong> : null}
                    </span>
                    {nestedConfig.type === "integer" || nestedConfig.type === "number" ? (
                      <input
                        type="number"
                        value={typeof nestedCurrent === "number" || typeof nestedCurrent === "string" ? nestedCurrent : ""}
                        onChange={(event) => setNestedField(field, nestedField, Number(event.target.value))}
                      />
                    ) : nestedConfig.type === "boolean" ? (
                      <select
                        value={nestedCurrent ? "true" : "false"}
                        onChange={(event) => setNestedField(field, nestedField, event.target.value === "true")}
                      >
                        <option value="true">启用</option>
                        <option value="false">关闭</option>
                      </select>
                    ) : (
                      <input
                        type={nestedSensitive ? "password" : "text"}
                        value={typeof nestedCurrent === "string" ? nestedCurrent : ""}
                        onChange={(event) => setNestedField(field, nestedField, event.target.value)}
                      />
                    )}
                  </label>
                );
              })}
            </div>
          );
        }

        return (
          <label key={field} className="plugin-config-field">
            <span>
              {fieldLabel(field, config)}
              {required ? <strong> *</strong> : null}
            </span>
            {field === "mcp_server" ? (
              <>
                <select value={typeof value === "string" ? value : ""} onChange={(event) => setField(field, event.target.value)}>
                  <option value="">选择 MCP Server</option>
                  {mcpServers.map((server) => (
                    <option key={server.name} value={server.name}>
                      {server.name}
                    </option>
                  ))}
                </select>
                {mcpServers.length === 0 ? (
                  <p className="inline-error">暂无可用 MCP Server，请先在「系统配置 → MCP Servers」维护真实服务实例。</p>
                ) : null}
              </>
            ) : isSecretRef ? (
              <>
                <select value={typeof value === "string" ? value : ""} onChange={(event) => setField(field, event.target.value)}>
                  <option value="">选择密钥引用</option>
                  {schema.auth_refs.map((ref) => (
                    <option key={ref} value={ref}>
                      {ref}
                    </option>
                  ))}
                </select>
                {schemaMisconfigured ? (
                  <p className="inline-error">
                    检测到敏感字段，schema 未声明 <code>format: "secret-ref"</code>，已强制走密钥引用选择器。请联系插件作者修正 schema。
                  </p>
                ) : null}
              </>
            ) : config.type === "integer" || config.type === "number" ? (
              <input
                type="number"
                value={typeof value === "number" || typeof value === "string" ? value : ""}
                onChange={(event) => setField(field, Number(event.target.value))}
              />
            ) : config.type === "boolean" ? (
              <select value={value ? "true" : "false"} onChange={(event) => setField(field, event.target.value === "true")}>
                <option value="true">启用</option>
                <option value="false">关闭</option>
              </select>
            ) : config.type === "array" ? (
              <input
                value={Array.isArray(value) ? value.join(",") : ""}
                onChange={(event) => setField(field, event.target.value.split(",").map((item) => item.trim()).filter(Boolean))}
              />
            ) : (
              <input
                value={typeof value === "string" ? value : ""}
                onChange={(event) => setField(field, event.target.value)}
              />
            )}
          </label>
        );
      })}
      {error ? <p className="inline-error">{error}</p> : null}
      {message ? <p className="form-status success">{message}</p> : null}
      <button type="button" className="primary-button compact" disabled={saving} onClick={save}>
        <span className="material-symbols-outlined">save</span>
        {saving ? "保存中..." : "保存配置"}
      </button>
      {readCapabilities.length ? (
        <div className="plugin-capability-test">
          <div className="section-mini-head">
            <h4>只读能力测试</h4>
            <span className="status-chip plain">真实调用</span>
          </div>
          <label className="plugin-config-field">
            <span>Capability</span>
            <select value={selectedCapabilityName} onChange={(event) => setSelectedCapabilityName(event.target.value)}>
              {readCapabilities.map((capability) => (
                <option key={capability.name} value={capability.name}>
                  {capability.name}
                </option>
              ))}
            </select>
          </label>
          <label className="plugin-config-field">
            <span>测试输入 JSON</span>
            <textarea value={testInput} onChange={(event) => setTestInput(event.target.value)} />
          </label>
          {testError ? <p className="inline-error">{testError}</p> : null}
          {testSimulatedNotice ? (
            <div className="plugin-test-warning">
              <span className="material-symbols-outlined">info</span>
              <p>{testSimulatedNotice}</p>
            </div>
          ) : null}
          {testResult ? <pre className="plugin-test-result">{testResult}</pre> : null}
          <button type="button" className="secondary-button compact" disabled={testing || !selectedCapabilityName} onClick={() => void runCapabilityTest()}>
            <span className="material-symbols-outlined">play_arrow</span>
            {testing ? "测试中..." : "测试只读能力"}
          </button>
        </div>
      ) : null}
    </div>
  );
}
