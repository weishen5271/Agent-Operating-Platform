import type { BusinessOutput } from "@/lib/api-client/types";

type Series = { name: string; values: Array<{ label: string; value: number }> };

export function ChartCanvas({ output }: { output: BusinessOutput }) {
  const series = (output.payload.series as Series[] | undefined) ?? [];
  const dataSource = (output.payload.data_source as string | undefined) ?? "未指定";
  const filters = (output.payload.filters as Record<string, unknown> | undefined) ?? {};
  const maxValue = series.flatMap((s) => s.values.map((v) => v.value)).reduce((a, b) => Math.max(a, b), 0) || 1;

  return (
    <div className="chart-canvas">
      <section className="panel-card">
        <div className="panel-header">
          <div>
            <h3>数据口径</h3>
            <p>展示数据源与过滤条件，确保口径可追溯。</p>
          </div>
        </div>
        <dl className="data-source-grid">
          <div>
            <dt>数据源</dt>
            <dd className="mono">{dataSource}</dd>
          </div>
          <div>
            <dt>过滤条件</dt>
            <dd className="mono">{Object.keys(filters).length ? JSON.stringify(filters) : "无"}</dd>
          </div>
        </dl>
      </section>

      <section className="panel-card">
        <div className="panel-header">
          <div>
            <h3>图表预览</h3>
            <p>占位条形图渲染（实际生产中嵌入图表引擎）。</p>
          </div>
        </div>
        {series.length ? (
          <div className="chart-stack">
            {series.map((s) => (
              <div key={s.name} className="chart-series">
                <h4>{s.name}</h4>
                <div className="chart-bars">
                  {s.values.map((point) => (
                    <div key={point.label} className="chart-bar-row">
                      <span className="chart-bar-label">{point.label}</span>
                      <div className="chart-bar-track">
                        <div
                          className="chart-bar-fill"
                          style={{ width: `${(point.value / maxValue) * 100}%` }}
                        />
                      </div>
                      <span className="chart-bar-value mono">{point.value}</span>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="row-meta">没有可渲染的序列，请在 payload.series 中添加数据。</p>
        )}
      </section>
    </div>
  );
}
