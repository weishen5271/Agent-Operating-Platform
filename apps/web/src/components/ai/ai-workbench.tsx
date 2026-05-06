"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { getAIRunTrace, listAIActions, listBusinessObjects, lookupBusinessObject, runAIAction } from "@/lib/api-client";
import type {
  AIActionDefinition,
  AIActionRunResponse,
  BusinessObjectDeclaration,
  TraceResponse,
} from "@/lib/api-client/types";

type ResultPayload = {
  facts?: unknown[];
  citations?: unknown[];
  reasoning_summary?: string;
  recommendations?: unknown[];
  action_plan?: unknown[];
  runtime_warnings?: string[];
  alarms?: unknown[];
};

function packageLabel(packageId: string): string {
  if (packageId === "industry.mfg_maintenance") return "制造业设备运维助手";
  return packageId;
}

function objectTypeLabel(objectType: string): string {
  if (objectType === "equipment") return "设备";
  return objectType;
}

function fieldLabel(field: string): string {
  const labels: Record<string, string> = {
    equipment_id: "设备 ID",
    fault_code: "故障码",
    last_n: "最近记录数",
    query: "检索查询",
  };
  return labels[field] ?? field;
}

function statusTone(status: string): string {
  if (status === "succeeded") return "success";
  if (status === "failed") return "danger";
  if (status === "running") return "warning";
  return "plain";
}

function displayValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return JSON.stringify(value, null, 2);
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

function extractLookupRecord(result: Record<string, unknown>): Record<string, unknown> | null {
  const direct = result.equipment;
  if (direct && typeof direct === "object" && !Array.isArray(direct)) {
    return direct as Record<string, unknown>;
  }
  const items = result.items;
  if (Array.isArray(items) && items[0] && typeof items[0] === "object" && !Array.isArray(items[0])) {
    return items[0] as Record<string, unknown>;
  }
  return null;
}

function itemTitle(item: unknown, fallback: string): string {
  if (!item || typeof item !== "object") return fallback;
  const record = item as Record<string, unknown>;
  return String(
    record.title ??
      record.summary ??
      record.text ??
      record.work_order_id ??
      record.id ??
      fallback,
  );
}

function itemMeta(item: unknown): string {
  if (!item || typeof item !== "object") return "";
  const record = item as Record<string, unknown>;
  const parts = [
    record.source_type,
    record.fault_code,
    record.equipment_id,
    record.evidence_count ? `${record.evidence_count} 条证据` : "",
  ].filter(Boolean);
  return parts.map(String).join(" · ");
}

function ResultSection({
  title,
  icon,
  items,
  emptyText,
}: {
  title: string;
  icon: string;
  items: unknown[];
  emptyText: string;
}) {
  return (
    <section className="ai-result-section">
      <div className="ai-result-section-head">
        <span className="material-symbols-outlined">{icon}</span>
        <h4>{title}</h4>
        <span className="status-chip plain">{items.length}</span>
      </div>
      {items.length ? (
        <div className="stack-list compact">
          {items.map((item, index) => (
            <article key={`${title}-${index}`} className="stack-item ai-result-item">
              <div>
                <strong>{itemTitle(item, `${title} ${index + 1}`)}</strong>
                {itemMeta(item) ? <p className="row-meta">{itemMeta(item)}</p> : null}
                {typeof item === "object" && item !== null ? (
                  <pre className="ai-json-snippet">{displayValue(item)}</pre>
                ) : (
                  <p>{displayValue(item)}</p>
                )}
              </div>
            </article>
          ))}
        </div>
      ) : (
        <div className="empty-distribution">{emptyText}</div>
      )}
    </section>
  );
}

export function AIWorkbench() {
  const [actions, setActions] = useState<AIActionDefinition[]>([]);
  const [businessObjects, setBusinessObjects] = useState<BusinessObjectDeclaration[]>([]);
  const [selectedPackageId, setSelectedPackageId] = useState("");
  const [selectedActionId, setSelectedActionId] = useState("");
  const [selectedObjectType, setSelectedObjectType] = useState("");
  const [objectId, setObjectId] = useState("");
  const [objectLookupResult, setObjectLookupResult] = useState<Record<string, unknown> | null>(null);
  const [objectLookupNotice, setObjectLookupNotice] = useState("");
  const [objectLookupError, setObjectLookupError] = useState("");
  const [checkingObject, setCheckingObject] = useState(false);
  const [inputValues, setInputValues] = useState<Record<string, string>>({});
  const [loadingActions, setLoadingActions] = useState(true);
  const [actionError, setActionError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [runResult, setRunResult] = useState<AIActionRunResponse | null>(null);
  const [trace, setTrace] = useState<TraceResponse | null>(null);
  const [traceError, setTraceError] = useState("");

  useEffect(() => {
    let alive = true;
    setLoadingActions(true);
    setActionError("");
    listAIActions()
      .then((response) => {
        if (!alive) return;
        setActions(response.items);
        const first = response.items[0];
        if (first) {
          setSelectedPackageId(first.package_id);
          setSelectedActionId(first.id);
          setSelectedObjectType(first.object_types[0] ?? "");
        }
      })
      .catch((exc) => {
        if (!alive) return;
        setActionError(exc instanceof Error ? exc.message : "AI 动作加载失败");
      })
      .finally(() => {
        if (alive) setLoadingActions(false);
      });
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    if (!selectedPackageId) {
      setBusinessObjects([]);
      return;
    }
    let alive = true;
    listBusinessObjects(selectedPackageId)
      .then((response) => {
        if (alive) setBusinessObjects(response.items);
      })
      .catch(() => {
        if (alive) setBusinessObjects([]);
      });
    return () => {
      alive = false;
    };
  }, [selectedPackageId]);

  const packageIds = useMemo(
    () => Array.from(new Set(actions.map((item) => item.package_id))).sort(),
    [actions],
  );

  const packageActions = useMemo(
    () => actions.filter((item) => item.package_id === selectedPackageId),
    [actions, selectedPackageId],
  );

  const selectedAction = useMemo(
    () => packageActions.find((item) => item.id === selectedActionId) ?? null,
    [packageActions, selectedActionId],
  );

  const objectTypes = selectedAction?.object_types ?? [];
  const selectedBusinessObject = useMemo(
    () => businessObjects.find((item) => item.type === selectedObjectType) ?? null,
    [businessObjects, selectedObjectType],
  );
  const hasLookupCapability = Boolean(selectedBusinessObject?.lookup_capability);
  const inputFields = useMemo(() => {
    if (!selectedAction) return [];
    return Array.from(
      new Set(
        [...selectedAction.required_inputs, ...selectedAction.optional_inputs].filter(
          (field) => field !== "equipment_id",
        ),
      ),
    );
  }, [selectedAction]);

  const payload = runResult?.output?.payload as ResultPayload | undefined;

  function handlePackageChange(value: string) {
    const nextAction = actions.find((item) => item.package_id === value);
    setSelectedPackageId(value);
    setSelectedActionId(nextAction?.id ?? "");
    setSelectedObjectType(nextAction?.object_types[0] ?? "");
    setRunResult(null);
    setTrace(null);
    setTraceError("");
    resetObjectLookup();
  }

  function handleActionChange(value: string) {
    const nextAction = packageActions.find((item) => item.id === value);
    setSelectedActionId(value);
    setSelectedObjectType(nextAction?.object_types[0] ?? "");
    setRunResult(null);
    setTrace(null);
    setTraceError("");
    resetObjectLookup();
  }

  function resetObjectLookup() {
    setObjectLookupResult(null);
    setObjectLookupNotice("");
    setObjectLookupError("");
  }

  function handleObjectIdChange(value: string) {
    setObjectId(value);
    resetObjectLookup();
  }

  function updateInput(field: string, value: string) {
    setInputValues((current) => ({ ...current, [field]: value }));
  }

  async function handleRunAction() {
    if (!selectedAction || !selectedObjectType) return;
    setSubmitting(true);
    setActionError("");
    setRunResult(null);
    setTrace(null);
    setTraceError("");
    try {
      const inputs = Object.fromEntries(
        Object.entries(inputValues)
          .map(([key, value]) => [key, value.trim()])
          .filter(([, value]) => value !== ""),
      );
      const response = await runAIAction(selectedAction.id, {
        package_id: selectedAction.package_id,
        source: "workspace",
        object: {
          object_type: selectedObjectType,
          object_id: objectId.trim(),
        },
        inputs,
        data_input: {
          mode: "platform_pull",
          context: {},
        },
      });
      setRunResult(response);
      if (response.run.trace_id) {
        try {
          const traceResponse = await getAIRunTrace(response.run.run_id);
          setTrace(traceResponse);
        } catch (exc) {
          setTraceError(exc instanceof Error ? exc.message : "Trace 加载失败");
        }
      }
    } catch (exc) {
      setActionError(exc instanceof Error ? exc.message : "AI Action 执行失败");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleLookupObject() {
    if (!selectedPackageId || !selectedObjectType || !objectId.trim()) return;
    setCheckingObject(true);
    setObjectLookupResult(null);
    setObjectLookupNotice("");
    setObjectLookupError("");
    try {
      const response = await lookupBusinessObject({
        package_id: selectedPackageId,
        object_type: selectedObjectType,
        object_id: objectId.trim(),
      });
      const record = extractLookupRecord(response.result);
      const total = Number(response.result.total ?? (record ? 1 : 0));
      if (!record || total === 0) {
        setObjectLookupError("未查询到该业务对象，请确认对象 ID 或外部系统权限。");
        return;
      }
      setObjectLookupResult(record);
      setObjectLookupNotice(findSimulatedNotice(response.result));
    } catch (exc) {
      setObjectLookupError(exc instanceof Error ? exc.message : "业务对象查询失败");
    } finally {
      setCheckingObject(false);
    }
  }

  const canSubmit =
    Boolean(selectedAction && selectedObjectType && objectId.trim()) &&
    (!hasLookupCapability || Boolean(objectLookupResult)) &&
    !submitting;

  return (
    <section className="page-section ai-workbench">
      <div className="page-head">
        <div className="page-head-meta">
          <div className="breadcrumbs">
            <span>运营驾驶舱</span>
            <span className="material-symbols-outlined">chevron_right</span>
            <span className="current">AI 业务工作台</span>
          </div>
          <h1>AI 业务工作台</h1>
          <p>围绕外部业务对象执行 AI 动作，保存结构化成果并保留 Trace 审计链路。</p>
        </div>
      </div>

      <div className="ai-workbench-grid">
        <section className="panel-card ai-control-panel">
          <div className="panel-header">
            <div>
              <h3>执行上下文</h3>
              <p>先校验外部业务对象，再执行结构化 AI 动作。</p>
            </div>
          </div>

          {loadingActions ? (
            <div className="trace-empty-state">
              <span className="material-symbols-outlined">progress_activity</span>
              <p>正在加载 AI 动作声明...</p>
            </div>
          ) : actions.length ? (
            <div className="form-grid ai-action-form">
              <label className="form-field form-field-full">
                <span>业务包</span>
                <select value={selectedPackageId} onChange={(event) => handlePackageChange(event.target.value)}>
                  {packageIds.map((packageId) => (
                    <option key={packageId} value={packageId}>
                      {packageLabel(packageId)} · {packageId}
                    </option>
                  ))}
                </select>
              </label>

              <label className="form-field">
                <span>对象类型</span>
                <select
                  value={selectedObjectType}
                  onChange={(event) => {
                    setSelectedObjectType(event.target.value);
                    resetObjectLookup();
                  }}
                >
                  {objectTypes.map((objectType) => (
                    <option key={objectType} value={objectType}>
                      {objectTypeLabel(objectType)}
                    </option>
                  ))}
                </select>
              </label>

              <label className="form-field">
                <span>对象 ID</span>
                <input
                  value={objectId}
                  placeholder="例如 EQ-CNC-650-01"
                  onChange={(event) => handleObjectIdChange(event.target.value)}
                />
              </label>

              {hasLookupCapability ? (
                <div className="ai-object-lookup form-field-full">
                  <div className="ai-object-lookup-head">
                    <div>
                      <strong>{selectedBusinessObject?.label ?? selectedObjectType}校验</strong>
                      <p className="row-meta">lookup: {selectedBusinessObject?.lookup_capability}</p>
                    </div>
                    <button
                      type="button"
                      className="secondary-button compact"
                      disabled={checkingObject || !objectId.trim()}
                      onClick={() => void handleLookupObject()}
                    >
                      <span className="material-symbols-outlined">{checkingObject ? "progress_activity" : "search"}</span>
                      {checkingObject ? "查询中..." : "查询对象"}
                    </button>
                  </div>
                  {objectLookupError ? <p className="inline-error">{objectLookupError}</p> : null}
                  {objectLookupNotice ? (
                    <div className="ai-warning-box compact">
                      <span className="material-symbols-outlined">info</span>
                      <div>
                        <strong>模拟数据提示</strong>
                        <p>{objectLookupNotice}</p>
                      </div>
                    </div>
                  ) : null}
                  {objectLookupResult ? (
                    <div className="ai-object-summary">
                      <strong>{String(objectLookupResult.name ?? objectLookupResult.equipment_id ?? objectId)}</strong>
                      <p>
                        {[
                          objectLookupResult.model,
                          objectLookupResult.line_code,
                          objectLookupResult.location,
                        ].filter(Boolean).map(String).join(" · ") || "已查询到对象。"}
                      </p>
                    </div>
                  ) : null}
                </div>
              ) : null}

              <label className="form-field form-field-full">
                <span>AI 动作</span>
                <select value={selectedActionId} onChange={(event) => handleActionChange(event.target.value)}>
                  {packageActions.map((action) => (
                    <option key={action.id} value={action.id}>
                      {action.label} · {action.id}
                    </option>
                  ))}
                </select>
              </label>

              {selectedAction ? (
                <div className="ai-action-summary form-field-full">
                  <div>
                    <strong>{selectedAction.label}</strong>
                    <p>{selectedAction.description || selectedAction.id}</p>
                  </div>
                  <span className={`status-chip ${selectedAction.risk_level === "low" ? "success" : "warning"}`}>
                    {selectedAction.risk_level}
                  </span>
                </div>
              ) : null}

              {inputFields.map((field) => (
                <label key={field} className="form-field">
                  <span>{fieldLabel(field)}</span>
                  <input
                    value={inputValues[field] ?? ""}
                    placeholder={field === "fault_code" ? "例如 AX-203" : field}
                    onChange={(event) => updateInput(field, event.target.value)}
                  />
                </label>
              ))}

              <div className="form-actions form-field-full">
                <button type="button" className="primary-button" disabled={!canSubmit} onClick={handleRunAction}>
                  <span className="material-symbols-outlined">{submitting ? "progress_activity" : "play_arrow"}</span>
                  {submitting ? "执行中..." : "执行 AI 动作"}
                </button>
              </div>
            </div>
          ) : (
            <div className="trace-empty-state">
              <span className="material-symbols-outlined">extension_off</span>
              <p>{actionError || "当前没有可执行的 AI Action 声明。"}</p>
            </div>
          )}

          {actionError && actions.length ? <p className="inline-error">{actionError}</p> : null}
        </section>

        <section className="panel-card ai-result-panel">
          <div className="panel-header">
            <div>
              <h3>执行结果</h3>
              <p>按事实、引用、推断、建议和行动计划分层展示。</p>
            </div>
            {runResult ? (
              <span className={`status-chip ${statusTone(runResult.run.status)}`}>{runResult.run.status}</span>
            ) : null}
          </div>

          {!runResult ? (
            <div className="trace-empty-state">
              <span className="material-symbols-outlined">route</span>
              <p>填写对象 ID 和动作参数后执行，结果会出现在这里。</p>
            </div>
          ) : runResult.run.status === "failed" ? (
            <div className="trace-empty-state">
              <span className="material-symbols-outlined">error</span>
              <p>{runResult.run.error_message || "AI Action 执行失败"}</p>
            </div>
          ) : (
            <div className="ai-result-layout">
              <div className="ai-run-meta">
                <span className="mono">{runResult.run.run_id}</span>
                <span>{objectTypeLabel(runResult.run.object_type)} / {runResult.run.object_id}</span>
                <span>{runResult.run.data_input_mode}</span>
              </div>

              {payload?.runtime_warnings?.length ? (
                <div className="ai-warning-box">
                  <span className="material-symbols-outlined">warning</span>
                  <div>
                    <strong>运行提示</strong>
                    {payload.runtime_warnings.map((warning) => (
                      <p key={warning}>{warning}</p>
                    ))}
                  </div>
                </div>
              ) : null}

              <section className="ai-reasoning-box">
                <h4>推断摘要</h4>
                <p>{payload?.reasoning_summary || runResult.output?.summary || "本次执行未返回推断摘要。"}</p>
              </section>

              <ResultSection
                title="报警记录"
                icon="notifications_active"
                items={payload?.alarms ?? []}
                emptyText="当前未返回 SCADA 报警记录。"
              />
              <ResultSection
                title="外部事实"
                icon="fact_check"
                items={payload?.facts ?? []}
                emptyText="当前未返回外部系统事实。"
              />
              <ResultSection
                title="知识引用"
                icon="menu_book"
                items={payload?.citations ?? []}
                emptyText="当前未返回知识引用。"
              />
              <ResultSection
                title="建议"
                icon="tips_and_updates"
                items={payload?.recommendations ?? []}
                emptyText="当前未返回建议。"
              />
              <ResultSection
                title="行动计划"
                icon="task_alt"
                items={payload?.action_plan ?? []}
                emptyText="当前未返回行动计划。"
              />

              <div className="ai-result-actions">
                {runResult.output ? (
                  <Link href={`/outputs/${encodeURIComponent(runResult.output.output_id)}`} className="secondary-button">
                    <span className="material-symbols-outlined">lightbulb</span>
                    查看业务成果
                  </Link>
                ) : null}
                {runResult.run.trace_id ? (
                  <span className="status-chip plain">Trace {runResult.run.trace_id}</span>
                ) : null}
              </div>
            </div>
          )}
        </section>

        <section className="panel-card ai-trace-panel">
          <div className="panel-header">
            <div>
              <h3>Trace</h3>
              <p>展示本次动作使用的 Skill、Capability 和 Tool。</p>
            </div>
          </div>
          {traceError ? <p className="inline-error">{traceError}</p> : null}
          {trace?.steps?.length ? (
            <div className="stack-list compact">
              {trace.steps.map((step, index) => (
                <article key={`${step.name}-${index}`} className="stack-item ai-trace-step">
                  <div>
                    <strong>{step.name}</strong>
                    <p>{step.summary}</p>
                    <p className="row-meta">
                      {step.node_type ?? "runtime"} · {step.ref ?? "runtime"}
                    </p>
                  </div>
                  <span className={`status-chip ${step.status === "failed" ? "danger" : step.status === "stub" ? "warning" : "success"}`}>
                    {step.status}
                  </span>
                </article>
              ))}
            </div>
          ) : (
            <div className="trace-empty-state">
              <span className="material-symbols-outlined">account_tree</span>
              <p>执行成功后会加载 Trace 步骤。</p>
            </div>
          )}
        </section>
      </div>
    </section>
  );
}
