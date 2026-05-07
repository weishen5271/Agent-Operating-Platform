import type { BusinessOutput } from "@/lib/api-client/types";

type RecordValue = Record<string, unknown>;

function asArray(value: unknown): unknown[] {
  if (Array.isArray(value)) return value;
  if (value === undefined || value === null || value === "") return [];
  return [value];
}

function asRecord(value: unknown): RecordValue {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as RecordValue) : {};
}

function textOf(value: unknown, fallback = "-"): string {
  if (typeof value === "string") return value || fallback;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (value === undefined || value === null) return fallback;
  return JSON.stringify(value);
}

function titleOf(value: unknown, fallback: string): string {
  const record = asRecord(value);
  return textOf(record.title ?? record.text ?? record.id ?? record.code, fallback);
}

function bodyOf(value: unknown): string {
  const record = asRecord(value);
  return textOf(
    record.description ??
      record.summary ??
      record.snippet ??
      record.reason ??
      record.recommendation ??
      record.action ??
      value,
    "",
  );
}

function EvidenceList({
  title,
  icon,
  items,
  empty,
}: {
  title: string;
  icon: string;
  items: unknown[];
  empty: string;
}) {
  return (
    <section className="panel-card">
      <div className="panel-header">
        <div>
          <h3>{title}</h3>
        </div>
        <span className="status-chip plain">{items.length}</span>
      </div>
      {items.length ? (
        <ul className="stack-list">
          {items.map((item, index) => (
            <li key={index} className="stack-item">
              <span className="material-symbols-outlined">{icon}</span>
              <div>
                <strong>{titleOf(item, `${title} ${index + 1}`)}</strong>
                {bodyOf(item) ? <p>{bodyOf(item)}</p> : null}
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <p className="row-meta">{empty}</p>
      )}
    </section>
  );
}

export function isStructuredAIOutput(output: BusinessOutput): boolean {
  return ["facts", "citations", "recommendations", "action_plan", "alarms", "runtime_warnings"].some(
    (key) => output.payload[key] !== undefined,
  );
}

export function StructuredAIOutput({ output }: { output: BusinessOutput }) {
  const facts = asArray(output.payload.facts);
  const citations = asArray(output.payload.citations);
  const alarms = asArray(output.payload.alarms);
  const recommendations = asArray(output.payload.recommendations);
  const actionPlan = asArray(output.payload.action_plan);
  const runtimeWarnings = asArray(output.payload.runtime_warnings);
  const reasoningSummary = textOf(output.payload.reasoning_summary ?? output.summary, "");
  const outputGuard = asRecord(output.payload.output_guard);
  const guardWarnings = asArray(outputGuard.warnings);

  return (
    <div className="structured-ai-output">
      <section className="panel-card">
        <div className="panel-header">
          <div>
            <h3>分析摘要</h3>
            <p>AI Action 输出的结构化摘要，结合外部系统事实、知识引用和运行提示生成。</p>
          </div>
        </div>
        <p className="decision-recommendation">{reasoningSummary || "暂无分析摘要。"}</p>
        {guardWarnings.length ? (
          <div className="plugin-test-warning">
            <span className="material-symbols-outlined">shield</span>
            <p>{guardWarnings.map((item) => textOf(item)).join("；")}</p>
          </div>
        ) : null}
      </section>

      <div className="dashboard-grid">
        <EvidenceList title="外部事实" icon="dataset" items={facts} empty="暂无外部系统事实。" />
        <EvidenceList title="知识引用" icon="article" items={citations} empty="暂无知识库引用。" />
      </div>

      {alarms.length ? (
        <EvidenceList title="SCADA 报警" icon="notifications_active" items={alarms} empty="暂无报警记录。" />
      ) : null}

      <section className="panel-card">
        <div className="panel-header">
          <div>
            <h3>建议与行动计划</h3>
            <p>建议只作为业务复核起点，高风险动作需进入草稿或审批。</p>
          </div>
          <span className="status-chip plain">{recommendations.length + actionPlan.length}</span>
        </div>
        <div className="dashboard-grid">
          <div>
            <h4 className="section-kicker">建议</h4>
            {recommendations.length ? (
              <ul className="stack-list compact">
                {recommendations.map((item, index) => (
                  <li key={index} className="stack-item">
                    <div>
                      <strong>{titleOf(item, `建议 ${index + 1}`)}</strong>
                      {bodyOf(item) ? <p>{bodyOf(item)}</p> : null}
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="row-meta">暂无建议。</p>
            )}
          </div>
          <div>
            <h4 className="section-kicker">行动计划</h4>
            {actionPlan.length ? (
              <ol className="next-steps-list">
                {actionPlan.map((item, index) => (
                  <li key={index}>{bodyOf(item) || titleOf(item, `步骤 ${index + 1}`)}</li>
                ))}
              </ol>
            ) : (
              <p className="row-meta">暂无行动计划。</p>
            )}
          </div>
        </div>
      </section>

      {runtimeWarnings.length ? (
        <section className="panel-card">
          <div className="panel-header">
            <div>
              <h3>运行提示</h3>
              <p>这些提示代表数据源、stub 或配置状态可能影响结论可信度。</p>
            </div>
            <span className="status-chip warning plain">{runtimeWarnings.length}</span>
          </div>
          <ul className="stack-list">
            {runtimeWarnings.map((item, index) => (
              <li key={index} className="stack-item">
                <span className="material-symbols-outlined">info</span>
                <div>
                  <p>{textOf(item)}</p>
                </div>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
