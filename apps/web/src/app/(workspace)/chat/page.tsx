import { ChatWorkbench } from "@/components/chat/chat-workbench";
import { Shell } from "@/components/shared/shell";

export default function ChatPage() {
  return (
    <Shell
      activeKey="chat"
      title="对话调试详情"
      searchPlaceholder="搜索 Trace ID..."
      tabs={[
        { label: "Trace 追踪", active: true },
        { label: "指标分析" },
        { label: "版本对比" },
      ]}
    >
      <ChatWorkbench />
    </Shell>
  );
}
