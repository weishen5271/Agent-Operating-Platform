"use client";

import { useState } from "react";

import { updateReleasePlan } from "@/lib/api-client";
import type { ReleasePlan } from "@/lib/api-client/types";

function statusTone(status: string): string {
  if (status.includes("完成")) return "success";
  if (status.includes("灰度")) return "warning";
  if (status.includes("回滚")) return "danger";
  return "info";
}

function nextState(item: ReleasePlan): { status: string; rollout_percent: number } {
  if (item.status === "待发布") return { status: "灰度中", rollout_percent: 10 };
  if (item.status === "灰度中") {
    const nextPercent = Math.min(100, Math.max(item.rollout_percent + 25, 50));
    return {
      status: nextPercent === 100 ? "已完成" : "灰度中",
      rollout_percent: nextPercent,
    };
  }
  return { status: item.status, rollout_percent: item.rollout_percent };
}

export function ReleaseTimeline({ initialReleases }: { initialReleases: ReleasePlan[] }) {
  const [releases, setReleases] = useState(initialReleases);
  const [busyId, setBusyId] = useState("");
  const [error, setError] = useState("");

  async function mutateRelease(release: ReleasePlan, payload: { status: string; rollout_percent: number }) {
    setBusyId(release.release_id);
    setError("");
    try {
      const updated = await updateReleasePlan(release.release_id, payload);
      setReleases((current) => current.map((item) => (item.release_id === updated.release_id ? updated : item)));
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "发布状态更新失败");
    } finally {
      setBusyId("");
    }
  }

  return (
    <section className="panel-card">
      <div className="panel-header">
        <div>
          <h3>Skill 灰度时间线</h3>
          <p>按单个 Skill 观察灰度比例、关键指标差异与回滚入口。</p>
        </div>
      </div>
      {error ? <p className="inline-error">{error}</p> : null}
      <div className="release-timeline">
        {releases.map((item) => {
          const next = nextState(item);
          const canAdvance = next.status !== item.status || next.rollout_percent !== item.rollout_percent;
          const busy = busyId === item.release_id;
          return (
            <article key={item.release_id} className="release-timeline-item">
              <div className="release-timeline-dot" aria-hidden="true" />
              <div>
                <strong>{item.skill}</strong>
                <p>
                  {item.package_name} · {item.version} · {item.started_at} · {item.metric_delta}
                </p>
                <div className="release-progress" aria-label={`灰度比例 ${item.rollout_percent}%`}>
                  <span style={{ width: `${item.rollout_percent}%` }} />
                </div>
              </div>
              <span className={`status-chip ${statusTone(item.status)}`}>{item.status}</span>
              <button
                type="button"
                className="ghost-button compact"
                disabled={!canAdvance || busy}
                onClick={() => mutateRelease(item, next)}
              >
                <span className="material-symbols-outlined">trending_up</span>
                推进
              </button>
              <button
                type="button"
                className="ghost-button compact"
                disabled={item.status === "已回滚" || busy}
                onClick={() => mutateRelease(item, { status: "已回滚", rollout_percent: 0 })}
              >
                <span className="material-symbols-outlined">undo</span>
                回滚
              </button>
            </article>
          );
        })}
        {!releases.length ? (
          <article className="stack-item">
            <div>
              <strong>暂无发布计划</strong>
              <p>创建发布计划后会在此展示灰度状态。</p>
            </div>
            <span className="status-chip plain">empty</span>
          </article>
        ) : null}
      </div>
    </section>
  );
}
