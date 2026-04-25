"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { hasValidStoredAuth } from "@/lib/api-client";

export function AuthGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [isClient, setIsClient] = useState(false);
  const [hasSession, setHasSession] = useState(false);

  useEffect(() => {
    setIsClient(true);
    if (!hasValidStoredAuth()) {
      router.replace("/login");
    } else {
      setHasSession(true);
    }
  }, [router]);

  // Show nothing while checking auth on client
  if (!isClient) {
    return null;
  }

  // If no valid session, will redirect in useEffect
  if (!hasSession) {
    return null;
  }

  return <>{children}</>;
}
