"use client";

import { useEffect, useState } from "react";

import { deleteMcpServer, listMcpServers, upsertMcpServer } from "@/lib/api-client";
import type { McpServer } from "@/lib/api-client/types";

type FormState = {
  name: string;
  transport: "streamable-http" | "http";
  endpoint: string;
  auth_ref: string;
  headersText: string;
  status: "active" | "disabled";
};

function blankForm(): FormState {
  return {
    name: "",
    transport: "streamable-http",
    endpoint: "",
    auth_ref: "",
    headersText: "{}",
    status: "active",
  };
}

function fromServer(server: McpServer): FormState {
  return {
    name: server.name,
    transport: server.transport,
    endpoint: server.endpoint,
    auth_ref: server.auth_ref,
    headersText: JSON.stringify(server.headers ?? {}, null, 2),
    status: server.status,
  };
}

export function McpServerManagement() {
  const [servers, setServers] = useState<McpServer[]>([]);
  const [form, setForm] = useState<FormState>(blankForm());
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function refresh() {
    setLoading(true);
    setError("");
    try {
      const response = await listMcpServers();
      setServers(response.servers);
      if (!form.name && response.servers[0]) {
        setForm(fromServer(response.servers[0]));
      }
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "MCP Server 加载失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function updateForm(patch: Partial<FormState>) {
    setForm((current) => ({ ...current, ...patch }));
  }

  async function save() {
    setSaving(true);
    setError("");
    setMessage("");
    try {
      const headers = JSON.parse(form.headersText || "{}") as Record<string, unknown>;
      if (!headers || typeof headers !== "object" || Array.isArray(headers)) {
        throw new Error("headers 必须是 JSON 对象");
      }
      const normalizedHeaders = Object.fromEntries(
        Object.entries(headers).map(([key, value]) => [key, String(value)]),
      );
      const saved = await upsertMcpServer({
        name: form.name.trim(),
        transport: form.transport,
        endpoint: form.endpoint.trim(),
        auth_ref: form.auth_ref.trim(),
        headers: normalizedHeaders,
        status: form.status,
      });
      setServers((current) => [saved, ...current.filter((item) => item.name !== saved.name)].sort((a, b) => a.name.localeCompare(b.name)));
      setForm(fromServer(saved));
      setMessage("MCP Server 已保存");
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "保存失败");
    } finally {
      setSaving(false);
    }
  }

  async function removeSelected() {
    const name = form.name.trim();
    if (!name) return;
    if (!window.confirm(`确认删除 MCP Server ${name}？`)) return;
    setSaving(true);
    setError("");
    setMessage("");
    try {
      await deleteMcpServer(name);
      const next = servers.filter((item) => item.name !== name);
      setServers(next);
      setForm(next[0] ? fromServer(next[0]) : blankForm());
      setMessage("MCP Server 已删除");
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "删除失败");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="panel-card">
      <div className="panel-header">
        <div>
          <h3>MCP Servers</h3>
          <p>维护平台注册的 MCP Server 实例，业务包通过名称引用。</p>
        </div>
        <button type="button" className="secondary-button compact" onClick={() => setForm(blankForm())}>
          <span className="material-symbols-outlined">add</span>
          新增
        </button>
      </div>

      <div className="tool-override-layout">
        <div className="stack-list">
          {loading ? (
            <article className="stack-item">
              <div>
                <strong>加载中</strong>
                <p>正在读取 MCP Server 注册表。</p>
              </div>
            </article>
          ) : null}
          {!loading && servers.length === 0 ? (
            <article className="stack-item">
              <div>
                <strong>暂无 MCP Server</strong>
                <p>保存真实的 MCP Server 配置后会显示在这里。</p>
              </div>
            </article>
          ) : null}
          {servers.map((server) => (
            <button
              key={server.name}
              type="button"
              className={`stack-item selectable ${form.name === server.name ? "active" : ""}`}
              onClick={() => setForm(fromServer(server))}
            >
              <div>
                <strong>{server.name}</strong>
                <p>{server.transport} · {server.endpoint}</p>
              </div>
              <span className={`status-chip ${server.status === "active" ? "success" : "plain"}`}>{server.status}</span>
            </button>
          ))}
        </div>

        <div className="plugin-config-form">
          <label className="plugin-config-field">
            <span>name *</span>
            <input value={form.name} onChange={(event) => updateForm({ name: event.target.value })} />
          </label>
          <label className="plugin-config-field">
            <span>transport *</span>
            <select value={form.transport} onChange={(event) => updateForm({ transport: event.target.value as FormState["transport"] })}>
              <option value="streamable-http">streamable-http</option>
              <option value="http">http</option>
            </select>
          </label>
          <label className="plugin-config-field">
            <span>endpoint *</span>
            <input value={form.endpoint} onChange={(event) => updateForm({ endpoint: event.target.value })} />
          </label>
          <label className="plugin-config-field">
            <span>auth_ref</span>
            <input value={form.auth_ref} onChange={(event) => updateForm({ auth_ref: event.target.value })} />
          </label>
          <label className="plugin-config-field">
            <span>headers JSON</span>
            <textarea value={form.headersText} onChange={(event) => updateForm({ headersText: event.target.value })} />
          </label>
          <label className="plugin-config-field">
            <span>status</span>
            <select value={form.status} onChange={(event) => updateForm({ status: event.target.value as FormState["status"] })}>
              <option value="active">active</option>
              <option value="disabled">disabled</option>
            </select>
          </label>
          {error ? <p className="inline-error">{error}</p> : null}
          {message ? <p className="form-status success">{message}</p> : null}
          <div className="form-actions">
            <button type="button" className="primary-button compact" disabled={saving} onClick={save}>
              <span className="material-symbols-outlined">save</span>
              {saving ? "保存中..." : "保存"}
            </button>
            <button type="button" className="secondary-button compact" disabled={saving || !form.name} onClick={removeSelected}>
              <span className="material-symbols-outlined">delete</span>
              删除
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}
