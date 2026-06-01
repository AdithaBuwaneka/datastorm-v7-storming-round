import type { Metadata } from "next";
import "./globals.css";
import { NavSidebar } from "@/components/nav-sidebar";

export const metadata: Metadata = {
  title: "Outlet Intelligence",
  description:
    "Decision-support web app for January 2026 outlet potential, trade-spend allocation, and explainable model insights.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-background text-foreground">
        <div className="flex">
          <NavSidebar />
          <main className="min-h-screen flex-1 p-6 lg:p-10">
            {children}
          </main>
        </div>
      </body>
    </html>
  );
}
