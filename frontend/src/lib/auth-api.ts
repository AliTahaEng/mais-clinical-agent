/**
 * Auth-specific API calls.
 * Separated from api-client.ts so auth logic doesn't circularly depend on itself.
 */

const BASE = "/api/v1/auth";

export interface AuthUser {
  id: string;
  email: string;
  username: string;
  role: "user" | "admin";
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user: AuthUser;
}

async function authFetch<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text();
    let detail = text;
    try {
      detail = JSON.parse(text)?.detail ?? text;
    } catch { /* ignore */ }
    throw new Error(detail || `HTTP ${res.status}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const authApi = {
  register(email: string, username: string, password: string): Promise<TokenResponse> {
    return authFetch("/register", {
      method: "POST",
      body: JSON.stringify({ email, username, password }),
    });
  },

  login(email: string, password: string): Promise<TokenResponse> {
    return authFetch("/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
  },

  logout(accessToken: string): Promise<void> {
    return authFetch("/logout", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${accessToken}`,
      },
    });
  },

  /** Uses the httpOnly refresh cookie — no token needed in headers. */
  refresh(): Promise<TokenResponse> {
    return authFetch("/refresh", { method: "POST" });
  },

  me(accessToken: string): Promise<AuthUser> {
    return authFetch("/me", {
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${accessToken}`,
      },
    });
  },
};
