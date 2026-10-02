export function NemiMark({ className = "h-8 w-8" }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden="true">
      <rect width="32" height="32" rx="10" className="fill-accent" />
      <circle cx="16" cy="16" r="6" className="fill-accent-ink" />
      <circle cx="16" cy="16" r="2.2" className="fill-sage" />
    </svg>
  );
}
