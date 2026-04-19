import { AuthGuard } from "@/components/shared/auth-guard";

export default function WorkspaceLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <AuthGuard>{children}</AuthGuard>;
}
