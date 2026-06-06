/**
 * DeepResearchArena Worker (Cloudflare Workers Static Assets + annotation backend).
 *
 * This is a real Worker (NOT a Pages `_worker.js`): it lives OUTSIDE the assets
 * directory (web/dist) and is referenced by web/dist/wrangler.jsonc as
 * `main: "../worker.js"`. A file literally named `_worker.js` inside the assets
 * dir is rejected by Wrangler ("Uploading a Pages _worker.js file as an asset"),
 * which is why the worker is named worker.js and kept one level up.
 *
 *   POST /api/annotate            body = Label JSON -> stored in KV (ANNOTATIONS)
 *   GET  /api/annotate?token=...  admin: returns all labels (token == ADMIN_TOKEN)
 *   GET  /api/annotate/count      public: how many labels collected (no payload)
 *
 * Bindings (web/dist/wrangler.jsonc):
 *   - assets.binding   = "ASSETS"
 *   - kv_namespaces[]  = { binding: "ANNOTATIONS", id: <KV id> }
 *   - ADMIN_TOKEN      (optional secret) for the admin GET
 */
const CORS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'POST, GET, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type',
}

function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { 'content-type': 'application/json', ...CORS },
  })
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url)

    // ---- live task status (box reporter -> KV -> /status page) ---------- //
    if (url.pathname === '/api/status') {
      if (request.method === 'OPTIONS') return new Response(null, { headers: CORS })
      if (request.method === 'POST') {
        const tok = request.headers.get('x-status-token') || url.searchParams.get('token')
        if (!env.STATUS_TOKEN || tok !== env.STATUS_TOKEN) return json({ error: 'forbidden' }, 403)
        let body
        try { body = await request.json() } catch { return json({ error: 'bad json' }, 400) }
        body._received = new Date().toISOString()
        try { await env.ANNOTATIONS.put('status:latest', JSON.stringify(body)) } catch { return json({ error: 'store failed' }, 500) }
        return json({ ok: true })
      }
      if (request.method === 'GET') {
        if (!env.ANNOTATIONS) return json({ error: 'backend not configured' }, 503)
        const v = await env.ANNOTATIONS.get('status:latest')
        return v
          ? new Response(v, { headers: { 'content-type': 'application/json', ...CORS } })
          : json({ error: 'no status yet' }, 404)
      }
      return json({ error: 'method not allowed' }, 405)
    }

    if (url.pathname === '/api/annotate' || url.pathname === '/api/annotate/count') {
      if (request.method === 'OPTIONS') return new Response(null, { headers: CORS })

      // public count (cheap signal that collection works; no label payload)
      if (url.pathname === '/api/annotate/count' && request.method === 'GET') {
        if (!env.ANNOTATIONS) return json({ count: 0, backend: false })
        let count = 0, cursor
        do {
          const l = await env.ANNOTATIONS.list({ prefix: 'label:', cursor, limit: 1000 })
          count += l.keys.length
          cursor = l.cursor
          if (l.list_complete) break
        } while (cursor)
        return json({ count, backend: true })
      }

      if (url.pathname === '/api/annotate' && request.method === 'POST') {
        if (!env.ANNOTATIONS) return json({ error: 'backend not configured' }, 503)
        let label
        try { label = await request.json() } catch { return json({ error: 'bad json' }, 400) }
        if (!label || !label.task_id || !label.winner) {
          return json({ error: 'missing task_id/winner' }, 400)
        }
        const ts = label.ts || new Date().toISOString()
        const id = `label:${ts}:${crypto.randomUUID()}`
        const rec = { ...label, _id: id }  // no IP stored (annotator field is enough; privacy)
        try {
          await env.ANNOTATIONS.put(id, JSON.stringify(rec))
        } catch {
          return json({ error: 'store failed' }, 500)
        }
        return json({ ok: true, id })
      }

      // admin retrieve all labels
      if (url.pathname === '/api/annotate' && request.method === 'GET') {
        const token = url.searchParams.get('token')
        if (!env.ADMIN_TOKEN || token !== env.ADMIN_TOKEN) return json({ error: 'forbidden' }, 403)
        if (!env.ANNOTATIONS) return json({ count: 0, labels: [] })
        const labels = []
        let cursor
        do {
          const l = await env.ANNOTATIONS.list({ prefix: 'label:', cursor, limit: 1000 })
          for (const k of l.keys) {
            const v = await env.ANNOTATIONS.get(k.name)
            if (v) { try { labels.push(JSON.parse(v)) } catch {} }
          }
          cursor = l.cursor
          if (l.list_complete) break
        } while (cursor)
        return json({ count: labels.length, labels })
      }

      return json({ error: 'method not allowed' }, 405)
    }

    // everything else: static assets
    return env.ASSETS.fetch(request)
  },
}
