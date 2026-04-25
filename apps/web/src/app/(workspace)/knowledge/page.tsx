"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";

import { KnowledgeConsole } from "@/components/knowledge/knowledge-console";
import {
  getAdminKnowledge,
  getAdminKnowledgeBases,
  getAdminWikiCompileRuns,
  getAdminWikiFileDistribution,
  getAdminWikiPages,
} from "@/lib/api-client";
import type {
  AdminKnowledgeResponse,
  AdminKnowledgeBasesResponse,
  AdminWikiCompileRunsResponse,
  AdminWikiFileDistributionResponse,
  AdminWikiPagesResponse,
} from "@/lib/api-client/types";

export default function KnowledgePage() {
  const searchParams = useSearchParams();
  const initialActiveTab = searchParams.get("tab") === "wiki" ? "wiki" : "rag";
  const explicitKnowledgeBase = searchParams.get("knowledgeBase");
  const selectedKnowledgeBase = explicitKnowledgeBase ?? "knowledge";
  const isWikiDetailView = initialActiveTab === "wiki" && Boolean(explicitKnowledgeBase);
  const isRagDetailView = initialActiveTab === "rag" && Boolean(explicitKnowledgeBase);
  const needsDetailData = isRagDetailView || isWikiDetailView;

  const [knowledgeBases, setKnowledgeBases] = useState<AdminKnowledgeBasesResponse["items"]>([]);
  const [sources, setSources] = useState<AdminKnowledgeResponse["sources"]>([]);
  const [wikiPages, setWikiPages] = useState<AdminWikiPagesResponse["pages"]>([]);
  const [wikiRuns, setWikiRuns] = useState<AdminWikiCompileRunsResponse["items"]>([]);
  const [wikiDistribution, setWikiDistribution] = useState<AdminWikiFileDistributionResponse | null>(null);

  useEffect(() => {
    let cancelled = false;

    void getAdminKnowledgeBases()
      .then((response) => {
        if (!cancelled) {
          setKnowledgeBases(response.items ?? []);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setKnowledgeBases([]);
        }
      });

    if (!needsDetailData) {
      setSources([]);
      setWikiPages([]);
      setWikiRuns([]);
      setWikiDistribution(null);
      return () => {
        cancelled = true;
      };
    }

    const ragPromise = isRagDetailView
      ? getAdminKnowledge(selectedKnowledgeBase).catch(() => null)
      : Promise.resolve(null);
    const wikiPagesPromise = isWikiDetailView
      ? getAdminWikiPages({ spaceCode: selectedKnowledgeBase }).catch(() => null)
      : Promise.resolve(null);
    const wikiRunsPromise = isWikiDetailView
      ? getAdminWikiCompileRuns().catch(() => null)
      : Promise.resolve(null);
    const wikiDistributionPromise = isWikiDetailView
      ? getAdminWikiFileDistribution({ spaceCode: selectedKnowledgeBase }).catch(() => null)
      : Promise.resolve(null);

    void Promise.all([ragPromise, wikiPagesPromise, wikiRunsPromise, wikiDistributionPromise]).then(
      ([knowledgeResponse, wikiPagesResponse, wikiRunsResponse, wikiDistributionResponse]) => {
        if (cancelled) {
          return;
        }
        setSources(knowledgeResponse?.sources ?? []);
        setWikiPages(wikiPagesResponse?.pages ?? []);
        setWikiRuns(wikiRunsResponse?.items ?? []);
        setWikiDistribution(wikiDistributionResponse);
      },
    );

    return () => {
      cancelled = true;
    };
  }, [needsDetailData, isRagDetailView, isWikiDetailView, selectedKnowledgeBase]);

  return (
    <KnowledgeConsole
      initialActiveTab={initialActiveTab}
      knowledgeBases={knowledgeBases}
      selectedKnowledgeBase={selectedKnowledgeBase}
      isWikiDetailView={isWikiDetailView}
      isRagDetailView={isRagDetailView}
      sources={sources}
      wikiPages={wikiPages}
      wikiRuns={wikiRuns}
      wikiDistribution={wikiDistribution}
    />
  );
}
