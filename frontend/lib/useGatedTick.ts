"use client";

import { useState } from "react";

export function useGatedTick(tick: number, isBusy: (gated: number) => boolean): number {
  const [gated, setGated] = useState(tick);
  if (gated !== tick && !isBusy(gated)) setGated(tick);
  return gated;
}
