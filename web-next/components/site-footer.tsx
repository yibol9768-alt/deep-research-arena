import Link from 'next/link';
import { GITHUB_URL } from '@/lib/constants';

export function SiteFooter() {
  return (
    <footer className="mt-20 border-t bg-background pt-10 pb-8">
      <div className="container-page grid grid-cols-2 md:grid-cols-4 gap-8 text-[13px]">
        <div className="col-span-2 md:col-span-1">
          <div className="flex items-center gap-2">
            <span className="inline-flex h-6 w-6 items-center justify-center rounded bg-primary text-[10px] font-bold text-primary-foreground">DR</span>
            <span className="font-semibold text-[14px]">Deep-Research Arena</span>
          </div>
          <p className="mt-3 text-[12.5px] leading-relaxed text-muted-foreground">
            Independent leaderboard for open-source deep-research agents. Same tasks, same scoring, public method.
          </p>
        </div>
        <FooterCol
          title="Browse"
          items={[
            { href: '/', label: 'Leaderboard' },
            { href: '/v4/', label: 'v4 (multi-pillar)' },
            { href: '/compare/', label: 'Compare LLMs' },
            { href: '/audit/', label: 'Audit' },
          ]}
        />
        <FooterCol
          title="Method"
          items={[
            { href: '/how-it-works/', label: 'How it works' },
            { href: '/about/', label: 'About' },
            { href: '/contribute/', label: 'Reproduce / contribute' },
          ]}
        />
        <div>
          <div className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Source</div>
          <ul className="space-y-1.5 text-foreground/80">
            <li>
              <a className="hover:text-foreground break-all" href={GITHUB_URL} target="_blank" rel="noopener">
                GitHub repository ↗
              </a>
            </li>
            <li>
              <a className="hover:text-foreground" href="/api/leaderboard.json">
                leaderboard.json
              </a>
            </li>
          </ul>
        </div>
      </div>
      <div className="container-page mt-8 flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-border/60 pt-5 text-[11.5px] text-muted-foreground">
        <span className="num-mono">composite_v2 = reachability · qm · nli · (0.4 url + 0.4 judge + 0.2 spec)</span>
        <span className="opacity-50">·</span>
        <span>Sandbox: Magento + Postmill + Kiwix</span>
        <span className="opacity-50">·</span>
        <span>Bradley-Terry Elo · bootstrap N=1000</span>
      </div>
    </footer>
  );
}

function FooterCol({ title, items }: { title: string; items: { href: string; label: string }[] }) {
  return (
    <div>
      <div className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">{title}</div>
      <ul className="space-y-1.5 text-foreground/80">
        {items.map((it) => (
          <li key={it.href}>
            <Link className="hover:text-foreground" href={it.href}>
              {it.label}
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
