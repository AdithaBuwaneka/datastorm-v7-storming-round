import type { Metadata } from "next";
import "./globals.css";
import { NavSidebar } from "@/components/nav-sidebar";
import { ThemeProvider } from "@/components/theme-provider";

export const metadata: Metadata = {
  title: "Outlet Intelligence",
  description:
    "Decision-support web app for January 2026 outlet potential, trade-spend allocation, and explainable model insights.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="min-h-screen bg-background text-foreground">
        <ThemeProvider
          attribute="class"
          defaultTheme="system"
          enableSystem
          disableTransitionOnChange
        >
          {/* The sidebar is position:fixed (locked to the viewport), so it
              is out of normal flow. We reserve its width with a left margin
              on large screens so the content never slides underneath it. */}
          <NavSidebar />
          <main className="min-h-screen min-w-0 overflow-x-hidden p-6 lg:ml-60 lg:p-10">
            {children}
          </main>
        </ThemeProvider>
      </body>
    </html>
  );
}
