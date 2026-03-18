"use client";

import Link from "next/link";
import { useRouter, usePathname } from "next/navigation";
import { useAuthStore } from "@/lib/stores/auth-store";
import { authApi } from "@/lib/auth-api";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { href: "/admin/dashboard", label: "Dashboard" },
  { href: "/admin/audit", label: "Audit Log" },
  { href: "/admin/sessions", label: "Sessions" },
  { href: "/admin/graph", label: "Graph Explorer" },
  { href: "/admin/ingest", label: "Ingest" },
  { href: "/admin/settings", label: "Settings" },
];

export default function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, accessToken, clearAuth } = useAuthStore();

  async function handleLogout() {
    try {
      if (accessToken) await authApi.logout(accessToken);
    } catch { /* best effort */ }
    clearAuth();
    router.push("/login");
  }

  return (
    <div className="min-h-screen flex">
      {/* Sidebar */}
      <aside className="w-56 bg-gray-900 text-white flex flex-col">
        <div className="p-5 border-b border-gray-700">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-md bg-blue-500 flex items-center justify-center text-white text-xs font-bold">
              M
            </div>
            <span className="font-semibold text-sm">MAIS Admin</span>
          </div>
        </div>

        <nav className="flex-1 p-3 space-y-1">
          {NAV_ITEMS.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "block px-3 py-2 rounded-md text-sm font-medium transition-colors",
                pathname === item.href
                  ? "bg-blue-600 text-white"
                  : "text-gray-300 hover:bg-gray-700 hover:text-white"
              )}
            >
              {item.label}
            </Link>
          ))}
        </nav>

        {/* Logged-in user info */}
        {user && (
          <div className="p-3 border-t border-gray-700">
            <div className="flex items-center gap-2 mb-2">
              <div className="w-7 h-7 rounded-full bg-blue-600 flex items-center justify-center text-white text-xs font-bold uppercase">
                {user.username[0]}
              </div>
              <div className="min-w-0">
                <div className="text-xs font-medium text-gray-100 truncate">{user.username}</div>
                <div className="text-xs text-gray-400">{user.role}</div>
              </div>
            </div>
            <button
              onClick={handleLogout}
              className="w-full text-xs text-gray-400 hover:text-red-400 transition-colors border border-gray-700 hover:border-red-800 rounded px-2 py-1.5 text-left"
            >
              Sign out
            </button>
          </div>
        )}

        {/* Back to clinician */}
        <div className="p-3 border-t border-gray-700">
          <Link
            href="/query"
            className="block text-xs text-gray-400 hover:text-gray-200 transition-colors"
          >
            ← Back to Clinical View
          </Link>
        </div>
      </aside>

      {/* Main */}
      <main className="flex-1 p-8 overflow-auto">
        {children}
      </main>
    </div>
  );
}
