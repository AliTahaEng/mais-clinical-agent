"use client";

/**
 * AuthProvider — mounts once at app root.
 * On load: silently calls /auth/refresh using the httpOnly cookie.
 * If the cookie is valid → user is logged in (token stored in memory).
 * If not → user stays logged out.
 */
import { useEffect } from "react";
import { authApi } from "@/lib/auth-api";
import { useAuthStore } from "@/lib/stores/auth-store";

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const { setAuth, clearAuth, setLoading } = useAuthStore();

  useEffect(() => {
    let cancelled = false;

    async function restoreSession() {
      try {
        const data = await authApi.refresh();
        if (!cancelled) {
          setAuth(data.user, data.access_token);
        }
      } catch {
        if (!cancelled) clearAuth();
      }
    }

    restoreSession();
    return () => { cancelled = true; };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return <>{children}</>;
}
