"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Store,
  BarChart3,
  MapPin,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { ThemeToggle } from "./theme-toggle";

const items = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/outlets", label: "Outlets", icon: Store },
  { href: "/insights", label: "Insights", icon: BarChart3 },
  { href: "/shop-map", label: "Shop Map", icon: MapPin },
] as const;

export function NavSidebar() {
  const pathname = usePathname() ?? "/";
  return (
    <aside className="fixed left-0 top-0 z-30 hidden h-screen w-60 flex-col overflow-y-auto border-r border-border bg-card lg:flex">
      <div className="px-5 py-6">
        <div className="flex items-center gap-2">
          <span className="grid h-8 w-8 place-items-center rounded-md bg-primary text-primary-foreground font-bold">
            OI
          </span>
          <span className="font-semibold leading-tight">
            Outlet
            <br />
            <span className="text-xs font-normal text-muted-foreground">
              Intelligence
            </span>
          </span>
        </div>
      </div>
      <nav className="flex flex-col gap-1 px-3">
        {items.map(({ href, label, icon: Icon }) => {
          const active =
            href === "/"
              ? pathname === "/"
              : pathname === href || pathname.startsWith(`${href}/`);
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
                active
                  ? "bg-primary/10 text-primary"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground",
              )}
            >
              <Icon className="h-4 w-4" />
              {label}
            </Link>
          );
        })}
      </nav>
      <div className="mt-auto px-5 py-4 flex flex-col gap-4">
        <ThemeToggle />
        <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
          Team DataX · v0.1
        </div>
      </div>
    </aside>
  );
}
