import Link from "next/link";
import { Button } from "@/components/ui/button";
import { fmtNumber } from "@/lib/utils";

function pageList(current: number, total: number): (number | "...")[] {
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1);
  const pages: (number | "...")[] = [1];
  const start = Math.max(2, current - 1);
  const end = Math.min(total - 1, current + 1);
  if (start > 2) pages.push("...");
  for (let p = start; p <= end; p++) pages.push(p);
  if (end < total - 1) pages.push("...");
  pages.push(total);
  return pages;
}

interface Props {
  page: number;
  totalPages: number;
  totalRows: number;
  label?: string;
  /** Function that returns the href for a given page number */
  pageHref: (p: number) => string;
}

export function PaginationBar({
  page,
  totalPages,
  totalRows,
  label = "rows",
  pageHref,
}: Props) {
  const pages = pageList(page, totalPages);
  return (
    <div className="mt-4 flex flex-wrap items-center justify-between gap-3 text-sm text-muted-foreground">
      <span>
        Page <span className="font-semibold text-foreground">{page}</span> of{" "}
        {fmtNumber(totalPages)} · {fmtNumber(totalRows)} {label}
      </span>
      <nav className="flex items-center gap-1">
        <Link href={pageHref(Math.max(1, page - 1))} aria-disabled={page <= 1}>
          <Button
            variant="outline"
            size="sm"
            disabled={page <= 1}
            className="h-8"
          >
            ← Prev
          </Button>
        </Link>

        {pages.map((p, i) =>
          p === "..." ? (
            <span
              key={`ell-${i}`}
              className="px-2 text-xs text-muted-foreground"
            >
              …
            </span>
          ) : (
            <Link key={p} href={pageHref(p)}>
              <Button
                variant={p === page ? "default" : "outline"}
                size="sm"
                className="h-8 min-w-8 px-2.5 font-mono text-xs"
              >
                {p}
              </Button>
            </Link>
          ),
        )}

        <Link
          href={pageHref(Math.min(totalPages, page + 1))}
          aria-disabled={page >= totalPages}
        >
          <Button
            variant="outline"
            size="sm"
            disabled={page >= totalPages}
            className="h-8"
          >
            Next →
          </Button>
        </Link>
      </nav>
    </div>
  );
}

export function buildPageHref(
  base: "/insights",
  view: string,
  page: number,
  extra?: Record<string, string>,
) {
  const sp = new URLSearchParams({ view });
  sp.set("page", String(page));
  if (extra) for (const [k, v] of Object.entries(extra)) sp.set(k, v);
  return `${base}?${sp.toString()}`;
}
