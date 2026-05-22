import { AlertTriangle } from 'lucide-react'

/**
 * DryRunBanner: a static, always-visible notice rendered at the top of the
 * homepage when the loaded leaderboard JSON carries either `_dry_run: true`
 * or a synthetic / placeholder `_schema_version`. The banner is intentionally
 * non-dismissible during the v3 dry-run phase so reviewers cannot miss it.
 */
export function DryRunBanner({
  isDryRun,
  schemaVersion,
}: {
  isDryRun: boolean
  schemaVersion?: string
}) {
  if (!isDryRun) return null

  return (
    <div
      role="status"
      className="border-b border-warn/30 bg-warn/10"
      data-component="dry-run-banner"
    >
      <div className="container flex flex-wrap items-center gap-3 py-2.5 text-xs sm:text-sm">
        <AlertTriangle className="h-4 w-4 shrink-0 text-warn" aria-hidden />
        <span className="font-semibold uppercase tracking-wider text-warn">
          DRY-RUN / SYNTHETIC DATA
        </span>
        <span className="text-ink/80">
          v3 dry-run output, awaiting real benchmark runs.
        </span>
        {schemaVersion ? (
          <span className="ml-auto rounded-pill bg-warn/15 px-2 py-0.5 text-[11px] font-medium text-warn tnum">
            schema {schemaVersion}
          </span>
        ) : null}
      </div>
    </div>
  )
}
