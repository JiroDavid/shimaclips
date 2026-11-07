const NORMAL = [
  "Fetching clips from Twitch...",
  "Sorting through the highlights...",
  "Counting clips by day...",
];

const SLOW = [
  "this streamer seems to be quite popular, loading clips will take a minute",
  "lots of clips to go through - hang tight",
  "Twitch is handing over a big pile of clips",
];

const VERY_SLOW = [
  "still going, this one is big",
  "still going, this one is big - thanks for waiting",
];

export function bannerMessage(elapsedMs: number, tick: number): { text: string; slow: boolean } {
  const slow = elapsedMs > 20000;
  const pool = elapsedMs > 90000 ? VERY_SLOW : slow ? SLOW : NORMAL;
  return { text: pool[tick % pool.length], slow };
}
