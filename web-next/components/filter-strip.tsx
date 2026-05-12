'use client';

import * as React from 'react';
import { cn } from '@/lib/utils';

interface BackboneItem {
  id: string;
  label: string;
  status: 'active' | 'queued';
  runs?: number;
}

const BACKBONES: BackboneItem[] = [
  { id: 'ds-flash', label: 'DeepSeek V4-flash', status: 'active' },
  { id: 'ds-pro', label: 'DeepSeek V4-pro', status: 'queued' },
  { id: 'gpt-4o-mini', label: 'GPT-4o-mini', status: 'queued' },
  { id: 'claude-sonnet-46', label: 'Claude Sonnet 4.6', status: 'queued' },
  { id: 'gemini-25-pro', label: 'Gemini 2.5 Pro', status: 'queued' },
];

export function FilterStrip({ shownAgents, totalAgents, updatedAt }: { shownAgents: number; totalAgents: number; updatedAt: string | null }) {
  return (
    <section className="mb-4">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2.5 rounded-lg border bg-card px-3 py-2.5">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="mr-1 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Backbone</span>
          {BACKBONES.map((bb) => {
            const active = bb.status === 'active';
            return (
              <button
                key={bb.id}
                type="button"
                disabled={!active}
                className={cn(
                  'inline-flex items-center rounded-full px-2.5 py-1 text-[12px] font-medium transition-colors',
                  active
                    ? 'bg-primary text-primary-foreground'
                    : 'border border-input bg-secondary/50 text-muted-foreground/70 cursor-not-allowed'
                )}
              >
                {bb.label}
              </button>
            );
          })}
        </div>
        <div className="ml-auto flex items-center gap-1.5 text-[12px] text-muted-foreground">
          <span className="num-mono">{shownAgents} of {totalAgents} agents</span>
          {updatedAt && (
            <>
              <span className="opacity-50">·</span>
              <span>updated {updatedAt}</span>
            </>
          )}
        </div>
      </div>
    </section>
  );
}
