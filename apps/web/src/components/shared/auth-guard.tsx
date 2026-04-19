"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

export function AuthGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [isClient, setIsClient] = useState(false);
  const [hasToken, setHasToken] = useState(false);

  useEffect(() => {
    setIsClient(true);
    const token = localStorage.getItem("auth_token");
    if (!token) {
      router.push("/login");
    } else {
      setHasToken(true);
    }
  }, [router]);

  // Show nothing while checking auth on client
  if (!isClient) {
    return null;
  }

  // If no token, will redirect in useEffect
  if (!hasToken) {
    return null;
  }

  return <>{children}</>;
}
