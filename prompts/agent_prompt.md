# Agent prompt template (the report writer under test)

> METHODOLOGY_REDESIGN_2026-07-03.md §5a. This is what a deep-research agent
> is given. It is a natural user request plus a light output contract, with
> NO quotas: no "cite at least N URLs", no "enumerate 40 products". Coverage
> is measured against the DB answer key, not demanded in the prompt. The same
> sandbox preamble is shown to every agent for fairness.

## Sandbox preamble (identical for all agents)

You have a search tool that reaches three sources, and nothing else is
online:

- an online store with product pages (names, prices, ratings, reviews),
- a discussion forum with threads, comments, and vote counts,
- an encyclopedia with reference articles.

When you use a page, link to it inline so the reader can check it. Only cite a
page if it genuinely backs what you say next to the link.

## The request

{USER_QUESTION}

## What they want back

{OUTPUT_CONTRACT}

Write it for the person who asked, not as a data dump. Lead with the answer
they came for, back each factual claim with the page it came from, and say
plainly where the sources are thin or disagree. Make it as long as it needs to
be and no longer.
