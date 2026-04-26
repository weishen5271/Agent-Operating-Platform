import type { BusinessOutput } from "@/lib/api-client/types";

type Section = { title?: string; body?: string };

export function ReportWorkspace({ output }: { output: BusinessOutput }) {
  const sections = (output.payload.sections as Section[] | undefined) ?? [];
  const abstract = (output.payload.abstract as string | undefined) ?? output.summary;

  return (
    <div className="report-workspace">
      <section className="panel-card">
        <div className="panel-header">
          <div>
            <h3>摘要</h3>
            <p>由对话总结生成，可在审阅阶段补充修订。</p>
          </div>
        </div>
        <p className="report-abstract">{abstract || "暂无摘要内容。"}</p>
      </section>

      <section className="panel-card">
        <div className="panel-header">
          <div>
            <h3>章节</h3>
            <p>每个章节可绑定证据并在审批通过后导出。</p>
          </div>
          <span className="status-chip plain">{sections.length} 章</span>
        </div>
        {sections.length ? (
          <div className="report-sections">
            {sections.map((section, index) => (
              <article key={index} className="report-section">
                <h4>
                  <span className="report-section-index">{index + 1}</span>
                  {section.title || `章节 ${index + 1}`}
                </h4>
                <p>{section.body || "（章节内容待补充）"}</p>
              </article>
            ))}
          </div>
        ) : (
          <p className="row-meta">尚未生成章节，请在对话页继续追问以丰富内容。</p>
        )}
      </section>
    </div>
  );
}
