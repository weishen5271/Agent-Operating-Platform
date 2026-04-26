"use client";

import { useState } from "react";

import { updateOutputGuardRule } from "@/lib/api-client";
import type { AdminSecurityResponse } from "@/lib/api-client/types";

type OutputGuardRuleRow = NonNullable<AdminSecurityResponse["redlines"]>[number];

const ACTION_OPTIONS = [
  "prepend_safety_warning",
  "append_warning",
  "block_or_escalate",
  "mask_sensitive_data",
  "downgrade_answer",
];

function blankRule(): OutputGuardRuleRow {
  return {
    rule_id: "",
    package_id: "industry.mfg",
    pattern: "",
    action: "block_or_escalate",
    source: "industry.mfg",
    enabled: true,
    recent_triggers: 0,
  };
}

export function OutputGuardRuleEditor({ initialRows }: { initialRows: OutputGuardRuleRow[] }) {
  const [rows, setRows] = useState<OutputGuardRuleRow[]>(initialRows);
  const [selected, setSelected] = useState<OutputGuardRuleRow>(initialRows[0] ?? blankRule());
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  function selectRule(row: OutputGuardRuleRow) {
    setSelected(row);
    setError("");
  }

  function createRule() {
    setSelected(blankRule());
    setError("");
  }

  function updateSelected(patch: Partial<OutputGuardRuleRow>) {
    setSelected((current) => ({ ...current, ...patch }));
  }

  async function save() {
    setSaving(true);
    setError("");
    try {
      const updated = await updateOutputGuardRule({
        rule_id: selected.rule_id,
        package_id: selected.package_id ?? "",
        pattern: selected.pattern,
        action: selected.action,
        source: selected.source,
        enabled: selected.enabled ?? true,
      });
      setRows((current) => {
        const exists = current.some((item) => item.rule_id === updated.rule_id);
        if (!exists) return [...current, updated];
        return current.map((item) => (item.rule_id === updated.rule_id ? updated : item));
      });
      setSelected(updated);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "保存失败");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="output-guard-layout">
      <div className="stack-list">
        {rows.map((item) => {
          const active = selected.rule_id === item.rule_id;
          return (
            <button
              key={item.rule_id}
              type="button"
              className={`stack-item stack-item-button ${active ? "selected" : ""}`}
              onClick={() => selectRule(item)}
            >
              <div>
                <strong>{item.rule_id}</strong>
                <p>{item.pattern}</p>
                <p className="row-meta">{item.source} · {item.action}</p>
              </div>
              <div className="stack-meta">
                <span className={`status-chip ${item.enabled === false ? "plain" : "warning"}`}>
                  {item.enabled === false ? "disabled" : "redline"}
                </span>
                <span className="mono">{item.recent_triggers} 次</span>
              </div>
            </button>
          );
        })}
        {!rows.length ? (
          <article className="stack-item">
            <div>
              <strong>暂无红线规则</strong>
              <p>新增规则后会在此展示。</p>
            </div>
            <span className="status-chip plain">empty</span>
          </article>
        ) : null}
      </div>

      <aside className="tool-override-editor output-guard-editor">
        <div className="section-mini-head">
          <h4>红线配置</h4>
          <button type="button" className="secondary-button compact" onClick={createRule}>
            <span className="material-symbols-outlined">add</span>
            新增
          </button>
        </div>
        <label className="plugin-config-field">
          <span>规则 ID</span>
          <input
            value={selected.rule_id}
            placeholder="mfg.output_guard.loto"
            onChange={(event) => updateSelected({ rule_id: event.target.value })}
          />
        </label>
        <label className="plugin-config-field">
          <span>业务包</span>
          <input
            value={selected.package_id ?? ""}
            placeholder="industry.mfg"
            onChange={(event) => updateSelected({ package_id: event.target.value })}
          />
        </label>
        <label className="plugin-config-field">
          <span>匹配模式</span>
          <textarea
            rows={3}
            value={selected.pattern}
            placeholder="断电|停机|挂牌上锁"
            onChange={(event) => updateSelected({ pattern: event.target.value })}
          />
        </label>
        <label className="plugin-config-field">
          <span>动作</span>
          <select value={selected.action} onChange={(event) => updateSelected({ action: event.target.value })}>
            {ACTION_OPTIONS.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </label>
        <label className="plugin-config-field">
          <span>来源</span>
          <input value={selected.source} onChange={(event) => updateSelected({ source: event.target.value })} />
        </label>
        <label className="tool-toggle-row">
          <input
            type="checkbox"
            checked={selected.enabled ?? true}
            onChange={(event) => updateSelected({ enabled: event.target.checked })}
          />
          <span>启用该红线规则</span>
        </label>
        {error ? <p className="inline-error">{error}</p> : null}
        <button type="button" className="primary-button compact" disabled={saving} onClick={save}>
          <span className="material-symbols-outlined">save</span>
          {saving ? "保存中..." : "保存规则"}
        </button>
      </aside>
    </div>
  );
}
