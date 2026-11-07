"use client";

import { useState } from "react";
import ClipReel from "@/components/ClipReel";
import type { Clip } from "@/lib/api";
import { rangeOfKey } from "@/lib/calendar";
import type { Selection } from "@/lib/selection";
import { useClips } from "@/lib/useClips";

type Sort = "views" | "newest";
type Range = { start?: string; end?: string };

type Common = {
  title: string;
  selection: Selection;
  onToggle: (clip: Clip) => void;
  loadingNote?: boolean;
  action?: React.ReactNode;
};

function ReelBody({
  login,
  range,
  tick,
  sort,
  onSortChange,
  yearFilter,
  ...rest
}: Common & {
  login: string;
  range: Range;
  tick: number;
  sort: Sort;
  onSortChange: (sort: Sort) => void;
  yearFilter?: { value: number | null; years: number[]; onChange: (year: number | null) => void };
}) {
  const { clips, total, exact, loading, error, showMore, hasMore } = useClips(login, range, tick, sort);
  return (
    <ClipReel
      {...rest}
      clips={clips}
      total={total}
      exact={exact}
      sort={sort}
      onSortChange={onSortChange}
      yearFilter={yearFilter}
      hasMore={hasMore}
      onShowMore={showMore}
      loading={loading}
      error={error}
    />
  );
}

export default function ReelSection({
  login,
  range,
  tick,
  yearOptions,
  ...rest
}: Common & {
  login: string;
  range: Range;
  tick: number;
  yearOptions?: number[];
}) {
  const [sort, setSort] = useState<Sort>("views");
  const [year, setYear] = useState<number | null>(null);
  const effectiveRange: Range = year !== null ? rangeOfKey(String(year)) : range;
  return (
    <ReelBody
      key={`${login}|${effectiveRange.start ?? ""}|${effectiveRange.end ?? ""}|${sort}`}
      {...rest}
      login={login}
      range={effectiveRange}
      tick={tick}
      sort={sort}
      onSortChange={setSort}
      yearFilter={yearOptions ? { value: year, years: yearOptions, onChange: setYear } : undefined}
    />
  );
}
