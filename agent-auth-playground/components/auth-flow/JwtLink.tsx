function KeyIcon() {
  return (
    <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <circle cx="7.5" cy="15.5" r="4" />
      <path d="M11 12l9-9" />
      <path d="M16 7l3 3" />
    </svg>
  );
}

export function JwtLink({ token, label }: { token: string; label: string }) {
  return (
    <a
      href={`https://www.jwt.io/#token=${encodeURIComponent(token)}`}
      target="_blank"
      rel="noopener noreferrer"
      title="Open token on jwt.io"
      className="inline-flex items-center gap-1 px-1.5 py-0.5 bg-amber-100 hover:bg-amber-200 border border-amber-300 rounded text-[10px] text-amber-900 font-medium no-underline"
    >
      <KeyIcon />
      {label}
    </a>
  );
}
