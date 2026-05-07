import { ApprovalCenter } from "@/components/admin/approval-center";
import { Shell } from "@/components/shared/shell";

export default function ApprovalsPage() {
  return (
    <Shell
      activeKey="security"
      title="审批确认页"
      searchPlaceholder="搜索草稿单或审批单..."
      tabs={[
        { label: "草稿确认", active: true },
        { label: "审批链状态" },
        { label: "执行记录" },
      ]}
    >
      <ApprovalCenter />
    </Shell>
  );
}
