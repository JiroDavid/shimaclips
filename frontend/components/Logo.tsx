export default function Logo({ className }: { className: string }) {
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img src="/shiba.png" alt="" width={512} height={512} className={className} />
  );
}
