import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export const fmtNumber = (n: number | null | undefined, digits = 0) =>
  n == null
    ? "—"
    : n.toLocaleString("en-LK", {
        minimumFractionDigits: digits,
        maximumFractionDigits: digits,
      });

export const fmtLKR = (n: number | null | undefined) =>
  n == null
    ? "—"
    : `LKR ${n.toLocaleString("en-LK", { maximumFractionDigits: 0 })}`;

export const fmtLitres = (n: number | null | undefined, digits = 0) =>
  n == null ? "—" : `${fmtNumber(n, digits)} L`;

export const fmtPct = (n: number | null | undefined, digits = 1) =>
  n == null ? "—" : `${(n * 100).toFixed(digits)}%`;
