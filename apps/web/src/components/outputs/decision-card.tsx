import type { BusinessOutput } from "@/lib/api-client/types";

type Alt = { title?: string; reason?: string };
type Risk = { title?: string; mitigation?: string };

export function DecisionCard({ output }: { output: BusinessOutput }) {
  const recommendation = (output.payload.recommendation as string | undefined) ?? output.summary;
  const alternatives = (output.payload.alternatives as Alt[] | undefined) ?? [];
  const risks = (output.payload.risks as Risk[] | undefined) ?? [];
  const nextSteps = (output.payload.next_steps as string[] | undefined) ?? [];

  return (
    <div className="decision-card">
      <section className="panel-card">
        <div className="panel-header">
          <div>
            <h3>推荐方案</h3>
            <p>从对话推理中提炼的首选方案，需结合证据链与风险评估。</p>
          </div>
        </div>
        <p className="decision-recommendation">{recommendation || "暂未生成推荐方案。"}</p>
      </section>

      <div className="dashboard-grid">
        <section className="panel-card">
          <div className="panel-header">
            <div>
              <h3>备选方案</h3>
            </div>
            <span className="status-chip plain">{alternatives.length}</span>
          </div>
          {alternatives.length ? (
            <ul className="stack-list">
              {alternatives.map((alt, idx) => (
                <li key={idx} className="stack-item">
                  <div>
                    <strong>{alt.title || `备选 ${idx + 1}`}</strong>
                    <p>{alt.reason || "未提供理由"}</p>
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <p className="row-meta">暂无备选方案。</p>
          )}
        </section>

        <section className="panel-card">
          <div className="panel-header">
            <div>
              <h3>风险与缓解</h3>
            </div>
            <span className="status-chip warning plain">{risks.length}</span>
          </div>
          {risks.length ? (
            <ul className="stack-list">
              {risks.map((risk, idx) => (
                <li key={idx} className="stack-item">
                  <div>
                    <strong>{risk.title || `风险 ${idx + 1}`}</strong>
                    <p>{risk.mitigation || "未提供缓解措施"}</p>
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <p className="row-meta">暂未识别风险。</p>
          )}
        </section>
      </div>

      <section className="panel-card">
        <div className="panel-header">
          <div>
            <h3>下一步</h3>
            <p>转入草稿包后可联动审批确认。</p>
          </div>
        </div>
        {nextSteps.length ? (
          <ol className="next-steps-list">
            {nextSteps.map((step, idx) => (
              <li key={idx}>{step}</li>
            ))}
          </ol>
        ) : (
          <p className="row-meta">尚未指定下一步动作。</p>
        )}
      </section>
    </div>
  );
}
