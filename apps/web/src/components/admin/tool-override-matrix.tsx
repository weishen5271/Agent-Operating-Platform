"use client";

import { useState } from "react";

import { updateToolOverride } from "@/lib/api-client";
import type { AdminSecurityResponse } from "@/lib/api-client/types";

type ToolOverrideRow = NonNullable<AdminSecurityResponse["tool_overrides"]>[number];

export function ToolOverrideMatrix({ initialRows }: { initialRows: ToolOverrideRow[] }) {
  const [rows, setRows] = useState<ToolOverrideRow[]>(initialRows);
  const [selected, setSelected] = useState<ToolOverrideRow | null>(initialRows[0] ?? null);
  const [quota, setQuota] = useState(String(initialRows[0]?.quota ?? ""));
  const [timeoutMs, setTimeoutMs] = useState(String(initialRows[0]?.timeout ?? ""));
  const [disabled, setDisabled] = useState(Boolean(initialRows[0]?.disabled));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  function selectRow(row: ToolOverrideRow) {
    setSelected(row);
    setQuota(String(row.quota ?? ""));
    setTimeoutMs(String(row.timeout ?? ""));
    setDisabled(Boolean(row.disabled));
    setError("");
  }

  async function save() {
    if (!selected) return;
    setSaving(true);
    setError("");
    try {
      const updated = await updateToolOverride({
        tenant_id: selected.tenant_id,
        tool_name: selected.tool_name,
        quota: quota ? Number(quota) : null,
        timeout: timeoutMs ? Number(timeoutMs) : null,
        disabled,
      });
      setRows((current) =>
        current.map((row) =>
          row.tenant_id === updated.tenant_id && row.tool_name === updated.tool_name ? updated : row,
        ),
      );
      setSelected(updated);
      setQuota(String(updated.quota ?? ""));
      setTimeoutMs(String(updated.timeout ?? ""));
      setDisabled(Boolean(updated.disabled));
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "保存失败");
    } finally {
      setSaving(false);
    }
  }

  if (!rows.length) {
    return (
      <div className="trace-empty-state">
        <span className="material-symbols-outlined">build</span>
        <p>暂无 Tool 覆盖配置。</p>
      </div>
    );
  }

  return (
    <div className="tool-override-layout">
      <div className="data-table">
        <div className="data-table-head five-cols">
          <span>Tool</span>
          <span>租户</span>
          <span>配额 / 分钟</span>
          <span>超时 (ms)</span>
          <span>状态</span>
        </div>
        {rows.map((item) => {
          const active = selected?.tool_name === item.tool_name && selected?.tenant_id === item.tenant_id;
          return (
            <button
              key={`${item.tool_name}-${item.tenant_id}`}
              type="button"
              className={`data-table-row five-cols table-row-button ${active ? "selected" : ""}`}
              onClick={() => selectRow(item)}
            >
              <strong>{item.tool_name}</strong>
              <span className="mono">{item.tenant_id}</span>
              <span className="mono">{item.quota ?? item.default_quota ?? "默认"}</span>
              <span className="mono">{item.timeout ?? item.default_timeout ?? "默认"}</span>
              <span className={`status-chip ${item.disabled ? "warning" : "success"}`}>
                {item.disabled ? "disabled" : item.overridden ? "overridden" : "default"}
              </span>
            </button>
          );
        })}
      </div>

      <aside className="tool-override-editor">
        <div className="section-mini-head">
          <h4>覆盖配置</h4>
          {selected ? <span className="status-chip plain">{selected.tool_name}</span> : null}
        </div>
        {selected ? (
          <>
            <label className="plugin-config-field">
              <span>配额 / 分钟</span>
              <input type="number" min={0} value={quota} onChange={(event) => setQuota(event.target.value)} />
            </label>
            <label className="plugin-config-field">
              <span>超时 (ms)</span>
              <input type="number" min={0} value={timeoutMs} onChange={(event) => setTimeoutMs(event.target.value)} />
            </label>
            <label className="tool-toggle-row">
              <input type="checkbox" checked={disabled} onChange={(event) => setDisabled(event.target.checked)} />
              <span>禁用该租户的 Tool</span>
            </label>
            {error ? <p className="inline-error">{error}</p> : null}
            <button type="button" className="primary-button compact" disabled={saving} onClick={save}>
              <span className="material-symbols-outlined">save</span>
              {saving ? "保存中..." : "保存覆盖"}
            </button>
          </>
        ) : (
          <p className="row-meta">选择一行后编辑覆盖值。</p>
        )}
      </aside>
    </div>
  );
}
