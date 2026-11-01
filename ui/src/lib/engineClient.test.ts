import { createClient, EngineError } from './engineClient'
import type { DownloadRequest, SearchResult } from './types'

function mockFetch(status: number, body: unknown) {
  return vi.fn(async () => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }))
}

const song: SearchResult = {
  kind: 'song', id: 'v1', title: 'La Graciosa', artist: 'Quevedo', album: '', duration_s: 258, views: 1,
  thumbnail: null, url: 'https://music.youtube.com/watch?v=v1', track_count: null, in_library: false
}
const req: DownloadRequest = { target: song, options: { format: 'mp3', quality: '320' }, force: false }

describe('engineClient', () => {
  it('sends X-Token and maps 409 duplicate', async () => {
    const fetch = mockFetch(409, { duplicate: { id: 1, title: 'La Graciosa' } })
    const c = createClient({ baseUrl: 'http://x', token: 't' }, fetch)
    expect(await c.download(req)).toEqual({ duplicate: expect.objectContaining({ id: 1 }) })
    const [url, init] = fetch.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe('http://x/jobs')
    expect((init.headers as Record<string, string>)['X-Token']).toBe('t')
    expect(JSON.parse(init.body as string)).toEqual({ type: 'download', request: req })
  })

  it('returns the job on success', async () => {
    const c = createClient({ baseUrl: 'http://x', token: 't' }, mockFetch(200, { job: { id: 'j1' } }))
    expect(await c.download(req)).toEqual({ job: { id: 'j1' } })
  })

  it('throws EngineError with the engine message', async () => {
    const c = createClient({ baseUrl: 'http://x', token: 't' }, mockFetch(502, { detail: { code: 'offline', message: 'No se pudo buscar.' } }))
    await expect(c.search('x', 'songs')).rejects.toMatchObject({ status: 502, code: 'offline', message: 'No se pudo buscar.' })
    await expect(c.search('x', 'songs')).rejects.toBeInstanceOf(EngineError)
  })

  it('encodes search params and history deletes', async () => {
    const fetch = mockFetch(200, [])
    const c = createClient({ baseUrl: 'http://x', token: 't' }, fetch)
    await c.search('la graciosa & co', 'videos')
    expect(fetch.mock.calls[0][0]).toBe('http://x/search?q=la+graciosa+%26+co&kind=videos')
    await c.deleteHistory('all')
    await c.deleteHistory([3, 4])
    const bodies = fetch.mock.calls.slice(1).map((c) => JSON.parse((c as unknown as [string, RequestInit])[1].body as string))
    expect(bodies).toEqual([{ all: true }, { ids: [3, 4] }])
  })

  it('retries a request when the engine is not reachable yet', async () => {
    let n = 0
    const fetch = vi.fn(async () => {
      if (n++ === 0) throw new TypeError('Failed to fetch')
      return new Response('{"ok":true}', { status: 200 })
    })
    const c = createClient({ baseUrl: 'http://x', token: 't' }, fetch, { retryDelayMs: 1 })
    expect(await c.health()).toEqual({ ok: true })
    expect(fetch).toHaveBeenCalledTimes(2)
  })
})
