export type Sort = "views" | "newest";

export function shouldFallBackToViews(sort: Sort, loading: boolean, exact: boolean): boolean {
  return sort === "newest" && !loading && !exact;
}
