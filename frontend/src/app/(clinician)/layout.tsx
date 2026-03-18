"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { SSEStatusIndicator } from "@/components/SSEStatusIndicator";
import { useAuthStore } from "@/lib/stores/auth-store";
import { authApi } from "@/lib/auth-api";

export default function ClinicianLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const { user, accessToken, clearAuth, isAdmin } = useAuthStore();

  async function handleLogout() {
    try {
      if (accessToken) await authApi.logout(accessToken);
    } catch { /* best effort */ }
    clearAuth();
    router.push("/login");
  }

  return (
    <div className="min-h-screen flex flex-col">
      <header className="sticky top-0 z-50 bg-white border-b border-gray-200 shadow-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            {/* Logo */}
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-lg bg-blue-600 flex items-center justify-center text-white font-bold text-sm">
                M
              </div>
              <span className="font-semibold text-gray-900">MAIS Clinical</span>
            </div>

            {/* Nav links */}
            <nav className="flex items-center gap-6">
              <Link
                href="/query"
                className="text-sm font-medium text-gray-600 hover:text-gray-900 transition-colors"
              >
                Query
              </Link>
              <Link
                href="/approvals"
                className="text-sm font-medium text-gray-600 hover:text-gray-900 transition-colors"
              >
                Approvals
              </Link>
              {isAdmin() && (
                <Link
                  href="/admin/dashboard"
                  className="text-sm font-medium text-gray-400 hover:text-gray-600 transition-colors"
                >
                  Admin ↗
                </Link>
              )}
            </nav>

            {/* Right — user + status */}
            <div className="flex items-center gap-4">
              <SSEStatusIndicator />
              {user && (
                <div className="flex items-center gap-3">
                  <div className="text-right hidden sm:block">
                    <div className="text-xs font-medium text-gray-900">{user.username}</div>
                    <div className="text-xs text-gray-400 capitalize">{user.role}</div>
                  </div>
                  <button
                    onClick={handleLogout}
                    className="text-xs text-gray-500 hover:text-red-600 transition-colors border border-gray-200 hover:border-red-200 rounded-md px-2.5 py-1.5"
                  >
                    Sign out
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      </header>

      <main className="flex-1 max-w-7xl mx-auto w-full px-4 sm:px-6 lg:px-8 py-8">
        {children}
      </main>
    </div>
  );
}
