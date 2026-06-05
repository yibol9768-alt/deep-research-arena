import { PageHero, MetricCard } from '@/components/layout/metric-card'
import { T } from '@/components/i18n/t'

export const dynamic = 'force-static'

const SYSTEMS = [
  {
    name: 'Magento shopping',
    nameZh: 'Magento 购物',
    port: ':7770',
    body: 'Product pages, prices, ratings, reviews, and marketing claims for evidence-heavy recommendation tasks.',
    bodyZh: '商品页面、价格、评分、评论与营销说辞，用于证据密集型的推荐类任务。',
  },
  {
    name: 'Postmill forum',
    nameZh: 'Postmill 论坛',
    port: ':9999',
    body: 'Threaded community discussions with scores, comments, sub-forums, and sentiment signals.',
    bodyZh: '带有评分、评论、子版块与情绪信号的串式社区讨论。',
  },
  {
    name: 'Kiwix Wikipedia',
    nameZh: 'Kiwix 维基百科',
    port: ':8090',
    body: 'Offline encyclopedia pages used to check definitions, timelines, and technical background.',
    bodyZh: '离线百科页面，用于核对定义、时间线与技术背景。',
  },
  {
    name: 'Search shim',
    nameZh: '搜索垫片',
    port: ':8081',
    body: 'Tavily and Firecrawl-compatible endpoints so external frameworks can run with minimal adapter code.',
    bodyZh: '兼容 Tavily 与 Firecrawl 的接口，让外部框架只需极少的适配代码即可运行。',
  },
  {
    name: 'DeepSeek proxy',
    nameZh: 'DeepSeek 代理',
    port: ':8088',
    body: 'OpenAI-compatible proxy that normalizes backend quirks for long-report generation.',
    bodyZh: '兼容 OpenAI 的代理，统一后端差异以支持长报告生成。',
  },
  {
    name: 'Verifier arena',
    nameZh: '校验器竞技场',
    port: 'local',
    body: 'Markdown, URL, checklist, fact graph, and judge outputs collected into pairwise battles.',
    bodyZh: '将 Markdown、URL、清单、事实图谱与评审输出汇集为两两对战。',
  },
]

export default function SandboxPage() {
  return (
    <>
      <PageHero
        eyebrow={<T en="Sandbox" zh="沙箱" />}
        title={<T en="A frozen mini-internet makes deep research reproducible." zh="一个冻结的迷你互联网让深度研究可复现。" />}
        intro={<T en="Agents browse a controlled stack instead of the live web. That makes every task rerunnable, every source reachable, and every citation audit possible." zh="智能体浏览的是受控的栈，而非真实的互联网。这让每个任务都可重跑、每个来源都可访问、每条引用都可审计。" />}
      >
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <MetricCard label={<T en="Containers" zh="容器" />} value="3+" detail={<T en="shopping, forum, wiki, plus shims" zh="购物、论坛、维基，外加垫片" />} />
          <MetricCard label={<T en="Sites" zh="站点" />} value="3" detail={<T en="cross-site evidence by design" zh="设计上即需跨站点取证" />} />
          <MetricCard label={<T en="API shape" zh="API 形态" />} value="OpenAI" detail={<T en="compatible model backend" zh="兼容的模型后端" />} />
          <MetricCard label={<T en="Search" zh="搜索" />} value="Tavily" detail={<T en="drop-in shim contract" zh="即插即用的垫片契约" />} />
        </div>
      </PageHero>

      <section className="container">
        <div className="card p-6">
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-6">
            {SYSTEMS.map((sys, i) => (
              <article key={sys.name} className="rounded-card border border-hairline bg-white p-5">
                <div className="flex items-center justify-between">
                  <span className="label-caps"><T en={`Node ${i + 1}`} zh={`节点 ${i + 1}`} /></span>
                  <span className="font-mono text-xs text-brand">{sys.port}</span>
                </div>
                <h2 className="mt-4 font-serif text-lg text-ink"><T en={sys.name} zh={sys.nameZh} /></h2>
                <p className="mt-2 text-xs leading-relaxed text-muted"><T en={sys.body} zh={sys.bodyZh} /></p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="container mt-10 grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="card p-7">
          <h2 className="font-serif text-h-sm text-ink">
            <T en="Why not the live web?" zh="为什么不用真实的互联网？" />
          </h2>
          <p className="mt-3 text-sm leading-relaxed text-muted">
            <T
              en="Live pages drift, search results personalize, and citations disappear. The sandbox trades breadth for auditability: each agent sees the same world, and each verifier can re-open the cited evidence."
              zh="真实页面会漂移变化，搜索结果会因人而异，引用也会失效消失。沙箱以广度换取可审计性：每个智能体面对同一个世界，每个校验器都能重新打开被引用的证据。"
            />
          </p>
        </div>
        <div className="card p-7">
          <h2 className="font-serif text-h-sm text-ink">
            <T en="Why keep web-shaped APIs?" zh="为什么保留类网页的 API？" />
          </h2>
          <p className="mt-3 text-sm leading-relaxed text-muted">
            <T
              en="Most deep-research frameworks already know Tavily, Firecrawl, and OpenAI-compatible chat endpoints. The shim lets them run against the benchmark with adapter code measured in dozens of lines."
              zh="大多数 Deep Research 框架已经熟悉 Tavily、Firecrawl 以及兼容 OpenAI 的对话接口。垫片让它们只需数十行适配代码即可在该基准上运行。"
            />
          </p>
        </div>
      </section>
    </>
  )
}
