import { AIWorkbench } from "@/components/ai/ai-workbench";
import { Shell } from "@/components/shared/shell";

export default function AIWorkbenchPage() {
  return (
    <Shell activeKey="ai-workbench" title="AI 业务工作台" searchPlaceholder="搜索业务对象、动作或 Run...">
      <AIWorkbench />
    </Shell>
  );
}
