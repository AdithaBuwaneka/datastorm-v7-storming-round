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
          <div className="flex max-w-full">
            <NavSidebar />
            <main className="min-w-0 flex-1 p-6 lg:p-10">
              {children}
            </main>
          </div>
        </ThemeProvider>
      </body>
    </html>
  );
}
