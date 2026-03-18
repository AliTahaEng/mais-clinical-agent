import type { Metadata } from "next";
import "./globals.css";
import { ReactQueryProvider } from "@/components/ReactQueryProvider";
import { AuthProvider } from "@/components/AuthProvider";

export const metadata: Metadata = {
  title: "MAIS — Medical AI System",
  description: "Medical Autonomous Intelligence System",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-gray-50 text-gray-900 antialiased">
        <ReactQueryProvider>
          <AuthProvider>{children}</AuthProvider>
        </ReactQueryProvider>
      </body>
    </html>
  );
}
