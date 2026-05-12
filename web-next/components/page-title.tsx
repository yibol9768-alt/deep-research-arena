import * as React from 'react';

export function PageTitle({ children, subtitle }: { children: React.ReactNode; subtitle?: React.ReactNode }) {
  return (
    <section className="mb-5">
      <h1 className="text-[28px] sm:text-[30px] font-bold leading-[1.15] tracking-tight text-foreground" style={{ maxWidth: '26ch' }}>
        {children}
      </h1>
      {subtitle && (
        <p className="mt-2.5 text-[14px] leading-relaxed text-foreground/80" style={{ maxWidth: '64ch' }}>
          {subtitle}
        </p>
      )}
    </section>
  );
}

export function Subnav({
  items,
}: {
  items: { href: string; label: string; current?: boolean; badge?: string }[];
}) {
  return (
    <nav className="mb-5 flex items-center gap-1 overflow-x-auto border-b" aria-label="Section nav">
      {items.map((it) => (
        <a
          key={it.href}
          href={it.href}
          className={
            'whitespace-nowrap px-3.5 py-2.5 text-[13px] font-medium border-b-2 -mb-px transition-colors ' +
            (it.current
              ? 'border-foreground text-foreground font-semibold'
              : 'border-transparent text-muted-foreground hover:text-foreground')
          }
        >
          {it.label}
          {it.badge && (
            <span className="ml-1.5 rounded bg-accent/15 px-1 py-0.5 text-[9px] font-bold uppercase tracking-wider text-accent">
              {it.badge}
            </span>
          )}
        </a>
      ))}
    </nav>
  );
}
