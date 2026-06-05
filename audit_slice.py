#!/usr/bin/env python3
import json, os, re, glob
from urllib.parse import unquote

GOLDEN_DIR = "/root/Desktop/lyb/deep_reserch/data/golden/deep"
CLEAN_DIR = "/root/Desktop/lyb/deep_reserch/data/golden/deep_clean"
os.makedirs(CLEAN_DIR, exist_ok=True)

TASK_IDS = ["dr_cross_deep_0001","dr_cross_deep_0008","dr_cross_deep_0016","dr_cross_deep_0024",
            "dr_cross_deep_0032","dr_cross_deep_0040","dr_cross_deep_0048","dr_cross_deep_0056",
            "dr_cross_deep_0064","dr_cross_deep_0072","dr_cross_deep_0080","dr_cross_deep_0088",
            "dr_cross_deep_0096"]

# map task_id -> golden filename (0001 has the .quotes variant)
GOLDEN_FILE = {tid: os.path.join(GOLDEN_DIR, tid + ".json") for tid in TASK_IDS}
GOLDEN_FILE["dr_cross_deep_0001"] = os.path.join(GOLDEN_DIR, "dr_cross_deep_0001.quotes.json")

# Per-task topic matchers. Each returns True if slug text (already lowercased, hyphens->spaces) is ON-topic.
# We judge by presence of topic-core tokens. 'any_kw' = on if any present (subject to excludes).
TOPICS = {
 "dr_cross_deep_0001": dict(
    topic="Consumer audio headphones (market intel)",
    kw=["headphone","earbud","earphone","earpiece","headset","bluetooth speaker","bluetooth headset",
        "noise cancel","noise-cancel","wireless audio","over ear","over-ear","in ear","in-ear",
        "audiophile","aptx","ldac","walkman","airpod","soundbar","mp3 player","wave clock radio",
        "audio","mixed by ali","extracting yt audio","turns articles into audio","wh-1000","bluetooth rechargeable speaker"],
    exclude=["motorcycle"],
    wiki_off=[]),
 "dr_cross_deep_0008": dict(
    topic="First-baby essentials fact-check (positioners, formula, car seat, sleep sack, bottle)",
    kw=["baby","infant","newborn","crib","diaper","formula","breastfeed","breast milk","breast pump",
        "swaddl","sleep sack","sleeping bag","colic","pacifier","car seat","carseat","isofix","positioner",
        "wedge pillow","nursing","bassinet","stroller","baby monitor","baby bottle","anti-colic","sids","postpartum"],
    exclude=["camel","car with really nice seats","song describes","love life","celebrity name","outrageous name",
             "name a newborn","names are an absolute","car with really","success formula","senna","investigative team"],
    wiki_off=[]),
 "dr_cross_deep_0016": dict(
    topic="Tenant rights comparison CA/NY/TX",
    kw=["landlord","tenant","evict","lease","security deposit","repair and deduct","repair-and-deduct",
        "habitability","renters insurance","renting","squatter","squatting","slumlord","eviction",
        "property code","money to my landlord","tenant's rights","tenant rights","premises liability",
        "quiet enjoyment","constructive eviction","rent control","rent regulation"],
    # shopping corpus has NO tenant-law books: filing cabinets ('legal letter size'), bookcases,
    # 'sister-in-law' gifts, 'law court spells', phone mount 'law compatible'. All keyword noise.
    shop_exclude=["filing cabinet","file cabinet","bookcase","book shelf","bookshelf","book case","book-shelf",
                  "sister in law","mother in law","in-law","court case spells","law compatible","popcorn",
                  "magazine file","file holder","file storage","makeup","mirror","candle"],
    exclude=["bar exam","real id","caf","deaf","guesthouse rental","business travel guesthouse","toothbrush container"],
    wiki_off=[]),
 "dr_cross_deep_0024": dict(
    topic="Cloud certification ladders AWS/GCP/Azure",
    # require genuine cloud-cert study context. Bare aws/s3/exam/devops matched model numbers,
    # ps3 slim, 'devops' pants brand, dental exam, paper underpants -> drop them.
    kw=["aws certification","aws exam","amazon web services","azure certification","azure exam",
        "google cloud certification","gcp exam","cloud computing","cloud certification","kubernetes",
        "site reliability engineering","cloud security exam","cloud practitioner","solutions architect exam",
        "aws certified","azure fundamentals","aws book","azure book","gcp book"],
    # almost all forum/shopping are off; require true cloud context. Plain "exam"/"book" not enough.
    exclude=["popcorn","mirror","blanket","body mist","face mask","sheet mask","bookshelf","book shelf","bookcase",
             "marine speaker","tattoo","decal","coat rack","hair clipper","beard","acne","cupcake","throw blanket",
             "azure art","azure hemp","azure hyaluronic","azure sherpa","ariana grande","stratus","cloud mobile",
             "cloud body","cloud blanket","cloud mirror","butterfinger","james bond","awful","female doctor",
             "winter coat","renewing real id","lease renewal","ct bar exam","geothermal","renewable","renewables",
             "power grid","solar","wind power","hvdc","exam in 20 days","world is awful","claude an ai",
             "chatgpt passes","mba exam","shifu framework","pixiu"],
    require_cloud=True,
    wiki_off=[]),
 "dr_cross_deep_0032": dict(
    topic="Vitamin D supplements (market intel)",
    kw=["vitamin d","vitamin-d","cholecalciferol","ergocalciferol","cod liver oil","fish oil","calcium",
        "rickets","osteoporosis","osteopenia","bone mineral","vitamin d3","vitamin d2","supplement","vitamin"],
    exclude=["deer tick","fluoride","levi","ai-generated","diet is not only","food storage"],
    require_vitd=True,
    wiki_off=[]),
 "dr_cross_deep_0040": dict(
    topic="History of vaccine development methods",
    kw=["vaccine","vaccination","vaccinat","immuniz","immunis","jenner","pasteur","sabin","salk","polio",
        "smallpox","mrna","rna vaccine","dna vaccine","inocul","attenuated vaccine","immunology","antigen",
        "antibody","adjuvant","moderna vaccine","johnson vaccine","j&j vaccine","flu vaccine","rabies vaccine"],
    # bare 'immune' matched 'immune to fall damage' / 'immune target' -> drop it
    exclude=["fall damage","heart disease breakthrough"],
    # shopping vaccine items are tshirts/tattoo/diagnostic -> off
    shop_exclude=["t-shirt","tee","hoodie","tattoo","makeup","trolley","salon","spa","dental tray","diagnostic cabl",
                  "diagnostic cable","logging device","surge protector","stool","cart","scanner","obd"],
    wiki_off=["edward_jenner_(writer)","edward_jenner_warren","thomas_jenner","jenner_(name)","jenner_(crater)",
              "gustav_jenner","edward_steptoe","lyc","marie_pasteur","jenner (writer)","jenner warren",
              "thomas jenner","jenner (name)","jenner (crater)","gustav jenner","edward steptoe","marie pasteur",
              "fran","virulent","jenner_(name)"],
    forum_off_default=True,
    wiki_off_extra=True),
 "dr_cross_deep_0048": dict(
    topic="Why SSDs slow down (causal)",
    # shopping: only genuine drives/storage devices count. forum 'trim'/'storage' threads are about
    # hedges/styrofoam/containers (auto-builder keyword error) -> require explicit drive/ssd context.
    kw=["ssd","solid state","solid-state","nvme","nand","flash memory","hard drive","hard disk","hdd",
        "wear leveling","firmware","garbage collection","thermal throttl","kingspec","firecuda","pcie",
        "m.2","optane","compact flash","memory card","sd card","sdhc","sdxc","seagate","western digital",
        "data storage device","external hard drive","flash drive","fragmentation","ssd performance"],
    shop_exclude=["screen protector","tempered glass","camera","dslr","powershot","coolpix","tweeter","webcam cover",
                  "key holder","cable case","sofa side table","laptop desk","speakers","filing cabinet","camera cover"],
    # forum threads here are all off-topic 'trim'/'storage' physical items; no genuine SSD discussion in slugs
    forum_kw_strict=["ssd","nvme","nand","solid state","solid-state","hard drive","hdd","flash drive","m.2","pcie ssd"],
    forum_off_default=True),
 "dr_cross_deep_0056": dict(
    topic="EV vs HEV vs HFCV comparison under $50k",
    # bare 'battery' matched Walkman/Surface/fan -> require vehicle/EV context
    # shopping had car accessories (phone holder/car fan/car blanket/RC connector) matching electric/hybrid car.
    kw=["electric vehicle","electric car","hybrid vehicle","fuel cell vehicle","hydrogen vehicle",
        "plug-in hybrid","plug in hybrid","ev battery","regenerative brak","afeela","green hydrogen",
        "clean hydrogen","considering buying an electric","eversource and electric","cleanest fully electric",
        "hydrogen powered","hydrogen filling","hydrogen production","hydrogen replace gas","fuel cell","hydrogen"],
    shop_exclude=["phone holder","car fan","car blanket","car seat fan","heated blanket","remote control",
                  "rc cars","connector anti spark","battery connector"],
    exclude=["range pakistan","bridger range","ragged range","karakoram","glacier","northern lights","gas range",
             "range oven","range hood","over-the-range","range microwave","humidity range","kilz","frigidaire range",
             "lab grown meat","slow fashion","sustainable bra","reusable bag","hairband","backpack","puck light",
             "leather backpack","clocked at 132","132 mph","insulated jacket","water pump","drone revolution",
             "killer ground drone","lose weight","co2 emissions to grow","sony walkman","surface pro","running a fan"],
    wiki_off=[]),
 "dr_cross_deep_0064": dict(
    topic="Endangered species recovery success stories",
    kw=["condor","ferret","whooping crane","red wolf","bison","elephant","przewalski","sea turtle","bald eagle",
        "giant panda","endangered species","extinct","conservation","biodiversity","ecosystem",
        "ecological restoration","invasive species","protected area","captive breeding","wildlife corridor",
        "iucn","chestnut tree","ocean dead zones","restore lost ecosystems","conservation status","national park"],
    # shopping 'wildlife' matched bird-watching telescopes/monoculars (optics); 'conservation' matched
    # a nail-polish 'conservation insert'. Genuine merch = national-park conservation apparel etc.
    shop_exclude=["telescope","monocular","binocular","spotting scope","trail camera","hunting camera",
                  "shower cap","star bird watching","game hunting","nail polish","refillable nail"],
    exclude=["100 million dollars","deserves to go extinct"],
    wiki_off=[],
    forum_off_default=False),
 "dr_cross_deep_0072": dict(
    topic="SBA small business loans catalog",
    kw=["sba","small business administration","small business loan","microloan","7(a)","504 loan","disaster loan",
        "working capital","line of credit","equipment financing","lender","lending","borrower","amortization",
        "business loan","get a 25k loan","want to start a business","loan repayment"],
    # 'podcast' / 'corporate purchases rant' are not SBA-loan discussions
    exclude=["podcast","rant about corporate"],
    shop_exclude=["storage bag","gift certificate","scratch off","printer","desktop","computer","jade roller",
                  "smart lock","projector","walkie","hat rack","table set","clock in","time clock","facial roller"],
    forum_off_default=True),
 "dr_cross_deep_0080": dict(
    topic="Evolution of social media regulation",
    # forum slugs are bare comments + off-topic (bank rant, bbby stock DD) -> require regulation/privacy context
    kw=["social media","data protection","section 230","gdpr","dmca","copyright","content moderation",
        "net neutrality","censorship","freedom of speech","cyberbull","deepfake","surveillance","data breach",
        "online legal","privacy regulation","internet regulation","online censorship"],
    exclude=["ranting on bank","bbby","trust me bro"],
    forum_off_default=True,
    wiki_off=[]),
 "dr_cross_deep_0088": dict(
    topic="Best online learning platforms for career changers",
    kw=["online learning","online education","e-learning","mooc","coursera","udemy","edx","bootcamp",
        "online course book","distance education","distance learning","professional development",
        "continuing education","lifelong learning","adult education","learning management","online degree",
        "study planner","career development book","learnprogramming","online tutoring"],
    # shopping 'online course' matched USB headsets 'for online courses' (not a learning platform).
    shop_exclude=["headset","headphone","blanket","lamp","desk","speaker","blackhead","pore vacuum"],
    forum_off_default=True,
    wiki_off=[]),
 "dr_cross_deep_0096": dict(
    topic="Retirement account types catalog",
    # bare 'tax' matched car luxury tax / property tax / solar -> require retirement/pension/account context
    kw=["retirement","401(k)","401k"," ira ","pension","roth","keogh","rrsp","annuity","social security",
        "defined benefit","defined contribution","tax-advantage","tax advantage","tax-defer","tax defer",
        "student loan repayment","penniless because her husband"],
    # 'pensioners' joke, generic tax-filing, luxury/property tax, solar -> off
    exclude=["luxury tax","solar power","cut taxes on homes","hike taxes","marijuana","revenue launches",
             "overpaid millions","trip down memory lane","tax filing work","tax preparer","who does your taxes",
             "need advice from tax professional"],
    # shopping all feng-shui wealth statues -> off
    shop_exclude=["statue","ornament","sculpture","feng shui","feng-shui","toad","spotting scope","decor","figurine",
                  "wu lou","gourd","pixiu","ruyi","wealth home","lucky","buddha","dragon","lion","monkey","rat",
                  "horse resin","elephant"],
    forum_off_default=True,
    wiki_off=[]),
}

def src_of(url):
    if "7770" in url: return "shopping"
    if "9999" in url: return "forum"
    if "8090" in url: return "wiki"
    return "other"

def slug_text(url, src):
    if src == "shopping":
        m = url.split("7770/")[-1]
        s = m[:-5] if m.endswith(".html") else m
    elif src == "forum":
        # /f/<forum>/<id>/<slug-or-comment>
        m = url.split("9999/f/")[-1]
        parts = m.split("/")
        forum = parts[0] if parts else ""
        slug = "/".join(parts[2:]) if len(parts) > 2 else ""
        s = (forum + " " + slug)
    elif src == "wiki":
        s = url.split("/A/")[-1]
    else:
        s = url
    s = unquote(s)
    s = s.replace("-", " ").replace("_", " ").replace("/", " ").lower()
    s = re.sub(r"\s+", " ", s).strip()
    return s

def forum_parts(url):
    m = url.split("9999/f/")[-1]
    parts = m.split("/")
    forum = parts[0] if parts else ""
    tid = parts[1] if len(parts) > 1 else ""
    slug = "/".join(parts[2:]) if len(parts) > 2 else ""
    is_comment = ("/-/comment/" in url) or slug.startswith("-/comment") or slug == "" or slug.startswith("-")
    return forum, tid, slug, is_comment

def on_topic(text, cfg, src):
    kws = cfg["kw"]
    if src == "forum" and "forum_kw_strict" in cfg:
        kws = cfg["forum_kw_strict"]
    # source-specific excludes
    if src == "shopping" and "shop_exclude" in cfg:
        for e in cfg["shop_exclude"]:
            if e in text:
                return False
    if "exclude" in cfg:
        for e in cfg["exclude"]:
            if e in text:
                return False
    for k in kws:
        if k in text:
            return True
    return False

def judge():
    rows = []
    for tid in TASK_IDS:
        cfg = TOPICS[tid]
        gf = GOLDEN_FILE[tid]
        with open(gf) as fh:
            data = json.load(fh)
        urls = data["must_cite_urls"]
        # build thread-id -> best slug map for forum, to propagate to comment urls
        thread_slug = {}
        for item in urls:
            u = item["url"] if isinstance(item, dict) else item
            if src_of(u) == "forum":
                forum, tid_f, slug, is_comment = forum_parts(u)
                if not is_comment and slug and not slug.startswith("-"):
                    thread_slug[(forum, tid_f)] = slug.replace("-", " ").replace("_", " ").lower()
        counts = {"shopping_on":0,"forum_on":0,"wiki_on":0}
        tot = {"shopping":0,"forum":0,"wiki":0}
        on_items = []
        wiki_off_terms = cfg.get("wiki_off", [])
        for item in urls:
            u = item["url"] if isinstance(item, dict) else item
            src = src_of(u)
            if src in tot: tot[src]+=1
            text = slug_text(u, src)
            decided_on = False
            if src == "forum":
                forum, tid_f, slug, is_comment = forum_parts(u)
                if is_comment:
                    # use propagated thread slug if available
                    propagated = thread_slug.get((forum, tid_f))
                    if propagated is not None:
                        judge_text = (forum.lower() + " " + propagated)
                        decided_on = on_topic(judge_text, cfg, src)
                    else:
                        # no slug anywhere for this thread -> cannot confirm on-topic from slug
                        decided_on = False
                else:
                    decided_on = on_topic(text, cfg, src)
            elif src == "wiki":
                wt = u.split("/A/")[-1]
                wl = unquote(wt).replace("_"," ").lower()
                off = False
                for o in wiki_off_terms:
                    if o.replace("_"," ").lower() in wl or o.lower() in wt.lower():
                        off = True; break
                if off:
                    decided_on = False
                else:
                    decided_on = on_topic(text, cfg, src) or True if not wiki_off_terms else on_topic(text,cfg,src)
                    # wiki articles for these tasks are curated; default on unless flagged off
                    if not wiki_off_terms:
                        decided_on = True
                    else:
                        decided_on = not off
            elif src == "shopping":
                decided_on = on_topic(text, cfg, src)
            if decided_on:
                if src == "shopping": counts["shopping_on"]+=1
                elif src == "forum": counts["forum_on"]+=1
                elif src == "wiki": counts["wiki_on"]+=1
                on_items.append(item)
        # write cleaned golden
        cleaned = dict(data)
        cleaned["must_cite_urls"] = on_items
        out = os.path.join(CLEAN_DIR, tid + ".json")
        with open(out, "w") as fh:
            json.dump(cleaned, fh, indent=2)
        # verdict
        n_must = len(urls)
        n_on = len(on_items)
        # a source counts as "healthy" if it has >=2 on-topic must-cite URLs
        healthy = {s: (v >= 2) for s, v in counts.items()}
        n_healthy = sum(1 for v in healthy.values() if v)
        # valid_sources: report every source that has >=1 on-topic (informational)
        valid_sources = [s.replace("_on","") for s,v in counts.items() if v>=1]
        forum_empty = counts["forum_on"] <= 1
        shop_ok = healthy["shopping_on"]
        wiki_ok = healthy["wiki_on"]
        if n_on == 0:
            verdict = "broken"
        elif forum_empty and shop_ok and wiki_ok:
            # forum is the dead dimension but shopping+wiki are both healthy
            verdict = "forum-invalid"
        elif n_healthy >= 2:
            verdict = "valid"
        elif n_healthy == 1:
            verdict = "mostly-off-topic"
        else:
            # nothing reaches 2 on-topic in any single source, but a few scattered hits
            verdict = "mostly-off-topic" if n_on >= 1 else "broken"
        rows.append(dict(task_id=tid, topic=cfg["topic"], n_must_cite=n_must, n_on_topic=n_on,
                         shopping_on=counts["shopping_on"], forum_on=counts["forum_on"], wiki_on=counts["wiki_on"],
                         valid_sources=valid_sources, verdict=verdict,
                         tot_shop=tot["shopping"], tot_forum=tot["forum"], tot_wiki=tot["wiki"]))
    return rows

if __name__ == "__main__":
    rows = judge()
    for r in rows:
        print(f"{r['task_id']} | on={r['n_on_topic']}/{r['n_must_cite']} "
              f"shop={r['shopping_on']}/{r['tot_shop']} forum={r['forum_on']}/{r['tot_forum']} "
              f"wiki={r['wiki_on']}/{r['tot_wiki']} | {r['verdict']} | {r['topic']}")
