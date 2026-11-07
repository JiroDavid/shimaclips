"use client";

import ClipReel from "@/components/ClipReel";
import type { Clip } from "@/lib/api";
import type { Selection } from "@/lib/selection";
import { useClips } from "@/lib/useClips";

export default function ReelSection({
  login,
  range,
  tick,
  title,
  selection,
  onToggle,
  loadingNote,
  action,
}: {
  login: string;
  range: { start?: string; end?: string };
  tick: number;
  title: string;
  selection: Selection;
  onToggle: (clip: Clip) => void;
  loadingNote?: boolean;
  action?: React.ReactNode;
}) {
  const { clips, total, loading, error, showMore, hasMore, capped } = useClips(login, range, tick);
  return (
    <ClipReel
      title={title}
      clips={clips}
      total={total}
      hasMore={hasMore}
      capped={capped}
      onShowMore={showMore}
      loading={loading}
      loadingNote={loadingNote}
      selection={selection}
      onToggle={onToggle}
      error={error}
      action={action}
    />
  );
}
