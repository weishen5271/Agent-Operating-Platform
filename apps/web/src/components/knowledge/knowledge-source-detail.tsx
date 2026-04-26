"use client";

import { useEffect, useState } from "react";

import { getAdminKnowledgeSourceAttributes } from "@/lib/api-client";
import type { AdminKnowledgeSourceAttributesResponse } from "@/lib/api-client/types";

function indexedTone(indexed: string): string {
  if (indexed === "hot") return "success";
  if (indexed === "warm") return "info";
  if (indexed === "cold") return "warning";
  return "";
}

export function KnowledgeSourceAttributes({ sourceId }: { sourceId: string }) {
  const [attributes, setAttributes] = useState<AdminKnowledgeSourceAttributesResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    getAdminKnowledgeSourceAttributes(sourceId)
      .then((response) => {
        if (!cancelled) setAttributes(response);
      })
      .catch((exc) => {
        if (!cancelled) {
          setAttributes(null);
          setError(exc instanceof Error ? exc.message : "扩展属性加载失败");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [sourceId]);

  return (
    <div className="knowledge-attributes-section">
      <div className="section-mini-head">
        <h4>扩展属性</h4>
        {attributes ? <span className="status-chip plain">{attributes.fields.length} 字段</span> : null}
      </div>
      {loading ? (
        <div className="empty-state">
          <strong>加载中</strong>
          <p>正在读取业务包声明的 chunk attributes schema。</p>
        </div>
      ) : error ? (
        <div className="empty-state">
          <strong>加载失败</strong>
          <p>{error}</p>
        </div>
      ) : attributes?.fields.length ? (
        <div className="data-table">
          <div className="data-table-head four-cols">
            <span>字段</span>
            <span>类型</span>
            <span>索引层级</span>
            <span>命中率</span>
          </div>
          {attributes.fields.map((field) => (
            <div key={field.field} className="data-table-row four-cols">
              <strong>{field.field}</strong>
              <span className="mono">{field.type}</span>
              <span className={`status-chip ${indexedTone(field.indexed)}`}>
                {field.indexed}
                {field.filter ? ` · ${field.filter}` : ""}
              </span>
              <span className="mono">
                {(field.hit_rate * 100).toFixed(0)}% ({field.hit_count}/{field.chunk_count})
              </span>
            </div>
          ))}
        </div>
      ) : (
        <div className="empty-state">
          <strong>暂无扩展属性</strong>
          <p>当前知识源尚未绑定 chunk attributes schema。</p>
        </div>
      )}
    </div>
  );
}
