import { getAdminKnowledge } from "@/lib/api-client";
import { KnowledgeIngestPanel } from "@/components/knowledge/knowledge-ingest-panel";
import { Shell } from "@/components/shared/shell";
import { knowledgeData } from "@/lib/workspace-fixtures";

export default async function KnowledgePage() {
  const knowledgeResponse = await getAdminKnowledge().catch(() => null);
  const sources = knowledgeResponse?.sources ?? [];
  const pipeline = sources.length
    ? [
        { label: "已接入数据源", value: `${sources.length} 个`, progress: 100 },
        { label: "知识切片", value: `${sources.reduce((sum, item) => sum + item.chunk_count, 0)} 块`, progress: 76 },
        { label: "运行中源", value: `${sources.filter((item) => item.status === "运行中").length} 个`, progress: 82 },
        { label: "索引健康度", value: "96.8%", progress: 96 },
      ]
    : knowledgeData.pipeline;

  const sourceRows = sources.length
    ? sources.map((item) => ({
        name: item.name,
        type: item.source_type,
        owner: item.owner,
        chunks: item.chunk_count,
        status: item.status,
      }))
    : knowledgeData.sources;

  function statusTone(status: string): string {
    if (status.includes("运行")) return "success";
    if (status.includes("重建") || status.includes("灰度")) return "warning";
    return "";
  }

  return (
    <Shell
      activeKey="knowledge"
      title="知识库治理"
      searchPlaceholder="搜索数据源、索引任务..."
      tabs={[
        { label: "流水线", active: true },
        { label: "质量实验室" },
        { label: "新鲜度" },
      ]}
    >
      <section className="page-section">
        <div className="page-head">
          <div className="page-head-meta">
            <div className="breadcrumbs">
              <span>能力中心</span>
              <span className="material-symbols-outlined">chevron_right</span>
              <span className="current">知识库治理</span>
            </div>
            <h1>知识库治理中心</h1>
            <p>贯穿文档清洗、切片、向量化与检索质量的一体化流水线，保障知识的新鲜与召回。</p>
          </div>
          <div className="page-head-actions">
            <button type="button" className="secondary-button">
              <span className="material-symbols-outlined">refresh</span>
              重新索引全部
            </button>
            <button type="button" className="primary-button">
              <span className="material-symbols-outlined">cloud_upload</span>
              上传新数据源
            </button>
          </div>
        </div>

        <div className="bento-grid three">
          <article className="stat-card hero">
            <div className="stat-card-head">
              <span className="stat-card-label">检索质量指数</span>
              <span className="stat-icon material-symbols-outlined">troubleshoot</span>
            </div>
            <strong>94.2%</strong>
            <p>向量召回 TOP-5 含正确答案</p>
            <span className="stat-trend">
              <span className="material-symbols-outlined">trending_up</span>
              +2.1% 较上周
            </span>
            <span className="material-symbols-outlined stat-card-glyph">troubleshoot</span>
          </article>
          <article className="stat-card">
            <div className="stat-card-head">
              <span className="stat-card-label">总切片规模</span>
              <span className="stat-icon material-symbols-outlined">grid_view</span>
            </div>
            <strong>10,662</strong>
            <p>覆盖 4 类数据源</p>
            <span className="stat-trend">
              <span className="material-symbols-outlined">trending_up</span>
              +1.4k 本周
            </span>
            <span className="material-symbols-outlined stat-card-glyph">grid_view</span>
          </article>
          <article className="stat-card">
            <div className="stat-card-head">
              <span className="stat-card-label">平均新鲜度</span>
              <span className="stat-icon material-symbols-outlined">schedule</span>
            </div>
            <strong>12h</strong>
            <p>距离最近一次重建</p>
            <span className="stat-trend">
              <span className="material-symbols-outlined">check_circle</span>
              维持 SLA
            </span>
            <span className="material-symbols-outlined stat-card-glyph">schedule</span>
          </article>
        </div>

        <KnowledgeIngestPanel />

        <div className="dashboard-grid">
          <section className="panel-card">
            <div className="panel-header">
              <div>
                <h3>处理流水线状态</h3>
                <p>统一查看文档清洗、切片、向量化和质量校验进度。</p>
              </div>
            </div>
            <div className="pipeline-grid">
              {pipeline.map((item) => (
                <article key={item.label} className="pipeline-card">
                  <span>{item.label}</span>
                  <strong>{item.value}</strong>
                  <div className="progress-rail">
                    <div className="progress-fill" style={{ width: `${item.progress}%` }} />
                  </div>
                </article>
              ))}
            </div>
          </section>

          <section className="panel-card">
            <div className="panel-header">
              <div>
                <h3>数据源列表</h3>
                <p>按所有权、切片规模和当前状态管理知识源。</p>
              </div>
            </div>
            <div className="stack-list">
              {sourceRows.map((item) => (
                <article key={item.name} className="stack-item">
                  <div>
                    <strong>{item.name}</strong>
                    <p>
                      {item.type} / {item.owner}
                    </p>
                  </div>
                  <div className="stack-meta">
                    <span className="mono">{item.chunks} 块</span>
                    <span className={`status-chip ${statusTone(item.status)}`}>{item.status}</span>
                  </div>
                </article>
              ))}
            </div>
          </section>
        </div>
      </section>
    </Shell>
  );
}
