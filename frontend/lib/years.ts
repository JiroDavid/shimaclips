import type { YearInfo } from "@/lib/api";

export function hasOlderApproximate(years: YearInfo[]): boolean {
  return years.some((y) => y.state === "approximate" && !y.enabled);
}
