import { KnowledgeConsole } from "@/components/knowledge/knowledge-console";
import {
  getAdminKnowledge,
  getAdminKnowledgeBases,
  getAdminWikiCompileRuns,
  getAdminWikiFileDistribution,
  getAdminWikiPages,
} from "@/lib/api-client";

type SearchParams = {
  tab?: string;
  knowledgeBase?: string;
};

type KnowledgePageProps = {
  searchParams?: Promise<SearchParams>;
};

export default async function KnowledgePage({ searchParams }: KnowledgePageProps) {
  const resolvedSearchParams = (await searchParams) ?? {};
  const initialActiveTab = resolvedSearchParams.tab === "wiki" ? "wiki" : "rag";
  const explicitKnowledgeBase = resolvedSearchParams.knowledgeBase;
  const selectedKnowledgeBase = explicitKnowledgeBase ?? "knowledge";
  const isWikiDetailView = initialActiveTab === "wiki" && Boolean(explicitKnowledgeBase);

  const knowledgeBasesResponse = await getAdminKnowledgeBases().catch(() => null);

  // Wiki 列表视图只需要知识库列表，详情视图才加载其他面板数据
  const needsDetailData = initialActiveTab === "rag" || isWikiDetailView;

  const [knowledgeResponse, wikiPagesResponse, wikiRunsResponse, wikiDistributionResponse] = needsDetailData
    ? await Promise.all([
        getAdminKnowledge(selectedKnowledgeBase).catch(() => null),
        getAdminWikiPages({ spaceCode: selectedKnowledgeBase }).catch(() => null),
        getAdminWikiCompileRuns().catch(() => null),
        getAdminWikiFileDistribution({ spaceCode: selectedKnowledgeBase }).catch(() => null),
      ])
    : [null, null, null, null];

  return (
    <KnowledgeConsole
      initialActiveTab={initialActiveTab}
      knowledgeBases={knowledgeBasesResponse?.items ?? []}
      selectedKnowledgeBase={selectedKnowledgeBase}
      isWikiDetailView={isWikiDetailView}
      sources={knowledgeResponse?.sources ?? []}
      wikiPages={wikiPagesResponse?.pages ?? []}
      wikiRuns={wikiRunsResponse?.items ?? []}
      wikiDistribution={wikiDistributionResponse}
    />
  );
}
