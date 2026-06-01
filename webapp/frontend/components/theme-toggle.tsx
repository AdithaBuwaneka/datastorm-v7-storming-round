"use client";

import * as React from "react";
import { Moon, Sun, Monitor } from "lucide-react";
import { useTheme } from "next-themes";
import { cn } from "@/lib/utils";

export function ThemeToggle() {
  const { theme, setTheme, mounted } = useTheme() as any;
  const [isMounted, setIsMounted] = React.useState(false);

  React.useEffect(() => {
    setIsMounted(true);
  }, []);

  if (!isMounted) {
    return <div className="h-9 w-full rounded-md border border-border bg-transparent"></div>;
  }

  return (
    <div className="flex w-full items-center justify-between rounded-md border border-border p-1">
      <button
        onClick={() => setTheme("light")}
        className={cn(
          "flex flex-1 items-center justify-center rounded px-2 py-1.5 text-xs transition-colors",
          theme === "light" ? "bg-muted text-foreground" : "text-muted-foreground hover:bg-muted/50 hover:text-foreground"
        )}
        title="Light Mode"
      >
        <Sun className="h-4 w-4" />
      </button>
      <button
        onClick={() => setTheme("dark")}
        className={cn(
          "flex flex-1 items-center justify-center rounded px-2 py-1.5 text-xs transition-colors",
          theme === "dark" ? "bg-muted text-foreground" : "text-muted-foreground hover:bg-muted/50 hover:text-foreground"
        )}
        title="Dark Mode"
      >
        <Moon className="h-4 w-4" />
      </button>
      <button
        onClick={() => setTheme("system")}
        className={cn(
          "flex flex-1 items-center justify-center rounded px-2 py-1.5 text-xs transition-colors",
          theme === "system" ? "bg-muted text-foreground" : "text-muted-foreground hover:bg-muted/50 hover:text-foreground"
        )}
        title="System Theme"
      >
        <Monitor className="h-4 w-4" />
      </button>
    </div>
  );
}
