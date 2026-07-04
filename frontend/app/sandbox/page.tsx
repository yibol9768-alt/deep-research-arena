import { PageHero, MetricCard } from '@/components/layout/metric-card'
import { T } from '@/components/i18n/t'

export const dynamic = 'force-static'

const SYSTEMS = [
  {
    name: 'Magento shopping',
    nameZh: 'Magento 购物',
    port: ':7770',
    body: '104,368 enumerated product pages with prices, ratings, reviews, and marketing claims for evidence-heavy recommendation tasks.',
    bodyZh: '104,368 个已枚举的商品页，含价格、评分、评论与营销说辞，用于证据密集型推荐任务。',
  },
  {
    name: 'Postmill forum',
    nameZh: 'Postmill 论坛',
    port: ':9999',
    body: '127,391 forum submissions across 95 forums, each post carrying a canonical forum name, with scores, comments, and sentiment signals.',
    bodyZh: '95 个论坛、127,391 条帖子，每帖带规范论坛名，含评分、评论与情绪信号。',
  },
  {
    name: 'Kiwix Wikipedia',
    nameZh: 'Kiwix 维基百科',
    port: ':8090',
    body: 'Offline encyclopedia pages for definitions and background. All 19,039,589 citable ZIM paths are enumerated in a 27MB Bloom filter (0.30% false-positive rate, no false negatives), so a cited article that does not exist is a decidable fabrication.',
    bodyZh: '离线百科页面，用于核对定义与技术背景。ZIM 全量枚举出的 19,039,589 条可引用路径收录在 27MB Bloom filter 中（假阳性率 0.30%，无假阴性），因此引用一篇不存在的文章即为可判定的编造。',
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
        title={<T en="The frozen sandbox." zh="冻结沙箱。" />}
        intro={<T en="Agents browse a controlled offline stack instead of the live web: a shopping site, a forum, and an offline Wikipedia, behind Tavily/Firecrawl-compatible search endpoints. Every task is rerunnable, and whether a cited page exists is decided by membership in an enumerated URL registry, with zero network requests." zh="智能体浏览的是受控的离线栈而非真实互联网：一个购物站、一个论坛和一份离线维基百科，通过兼容 Tavily/Firecrawl 的搜索接口访问。每个任务都可重跑；一条引用的页面是否存在，由它是否属于已枚举的 URL 注册表来判定，全程不发任何网络请求。" />}
      >
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <MetricCard label={<T en="Products" zh="商品页" />} value="104,368" detail={<T en="enumerated product pages" zh="已枚举的商品页" />} />
          <MetricCard label={<T en="Forum posts" zh="论坛帖" />} value="127,391" detail={<T en="across 95 forums" zh="分布于 95 个论坛" />} />
          <MetricCard label={<T en="Wiki paths" zh="维基路径" />} value="19M+" detail={<T en="full ZIM in a 27MB Bloom filter" zh="ZIM 全量枚举，27MB Bloom filter" />} />
          <MetricCard label={<T en="Reachability" zh="可达性" />} value="0 HTTP" detail={<T en="citations checked as set membership" zh="引用以集合成员查询判定" />} />
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
              en="Live pages drift, search results personalize, and citations disappear. The sandbox trades breadth for auditability: every agent sees the same frozen world, and a citation either belongs to the enumerated URL registry or it does not, decided without a single network request."
              zh="真实页面会漂移，搜索结果因人而异，引用也会失效。沙箱以广度换取可审计性：每个智能体面对同一个冻结世界，一条引用要么属于已枚举的 URL 注册表，要么不属于，判定过程不发任何网络请求。"
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
