// 即時財經快報：鉅亨網 RSS（robots.txt 允許），伺服器端每個分類最多 3 分鐘抓一次，所有讀者共用。
//   GET /api/news?cat=all|tw_stock|wd_stock|headline

const FEEDS = { tw_stock: "台股", wd_stock: "國際", headline: "頭條" };
const CACHE_MS = 3 * 60_000;
const UA = "craig-finance-hub/1.0 (+https://github.com/craigshih)";
const memo = {};

const unwrap = (s) => (s || "").replace(/<!\[CDATA\[|\]\]>/g, "").trim();
const decode = (s) =>
  s.replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&amp;/g, "&");
const tag = (block, name) => {
  const m = block.match(new RegExp(`<${name}[^>]*>([\\s\\S]*?)</${name}>`));
  return m ? decode(unwrap(m[1])) : "";
};

export function parseRss(xml, feed) {
  return [...xml.matchAll(/<item>([\s\S]*?)<\/item>/g)].map(([, b]) => {
    const thumb = b.match(/<media:thumbnail[^>]*url="([^"]+)"/);
    const summary = tag(b, "description").replace(/<[^>]+>/g, "").replace(/\s+/g, " ");
    return {
      title: tag(b, "title"),
      url: tag(b, "link"),
      time: new Date(tag(b, "pubDate")).toISOString(),
      category: tag(b, "category"),
      feed,
      feed_label: FEEDS[feed],
      thumb: thumb ? thumb[1] : null,
      keywords: tag(b, "media:keywords").split(",").map((k) => k.trim()).filter(Boolean),
      summary: summary.length > 110 ? summary.slice(0, 110) + "…" : summary,
    };
  }).filter((i) => i.title && i.url.startsWith("https://news.cnyes.com/"));
}

async function feedItems(feed) {
  const m = memo[feed];
  if (m && Date.now() - m.at < CACHE_MS) return m.items;
  try {
    const res = await fetch(`https://news.cnyes.com/rss/v1/news/category/${feed}`, { headers: { "User-Agent": UA } });
    if (!res.ok) throw new Error(`${feed} ${res.status}`);
    const items = parseRss(await res.text(), feed);
    memo[feed] = { items, at: Date.now() };
    return items;
  } catch (exc) {
    console.error(exc);
    return m ? m.items : []; // 來源暫時失敗時沿用上一次的
  }
}

export async function onRequestGet({ request }) {
  const cat = new URL(request.url).searchParams.get("cat") || "all";
  const feeds = cat === "all" ? Object.keys(FEEDS) : FEEDS[cat] ? [cat] : null;
  if (!feeds) return Response.json({ error: "沒有這個分類" }, { status: 400 });
  const seen = new Set();
  const items = (await Promise.all(feeds.map(feedItems))).flat()
    .filter((i) => !seen.has(i.url) && seen.add(i.url))
    .sort((a, b) => b.time.localeCompare(a.time))
    .slice(0, 80);
  return Response.json({ updated: new Date().toISOString(), items },
    { headers: { "Cache-Control": "public, max-age=60" } });
}
