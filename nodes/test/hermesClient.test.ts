import { describe, it, expect, vi } from 'vitest'
import { chatCompletion, HermesError, normalizeBaseUrl } from '../src/nodes/shared/hermesClient'

const base = { baseUrl: 'http://hermes:8642', apiKey: 'secret-key', prompt: 'Bonjour', timeoutMs: 1000 }

const jsonResponse = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
const okBody = { choices: [{ message: { content: 'pong', reasoning_content: 'je réfléchis' } }], usage: { total_tokens: 12 } }

const failsWith = async (p: Promise<unknown>, code: HermesError['code'], pattern?: RegExp) => {
    const err = await p.then(
        () => null,
        (e) => e
    )
    expect(err).toBeInstanceOf(HermesError)
    expect(err.code).toBe(code)
    if (pattern) expect(err.message).toMatch(pattern)
}

describe('normalizeBaseUrl', () => {
    it.each([
        ['http://hermes:8642', 'http://hermes:8642'],
        ['http://hermes:8642/', 'http://hermes:8642'],
        ['http://hermes:8642/v1', 'http://hermes:8642'],
        [' http://hermes:8642/v1/ ', 'http://hermes:8642']
    ])('%s -> %s', (input, expected) => expect(normalizeBaseUrl(input)).toBe(expected))
})

describe('chatCompletion', () => {
    it('renvoie le contenu, le raisonnement et la consommation', async () => {
        const fetchImpl = vi.fn().mockResolvedValue(jsonResponse(okBody))
        const result = await chatCompletion({ ...base, fetchImpl })
        expect(result).toEqual({ content: 'pong', reasoning: 'je réfléchis', usage: { total_tokens: 12 } })
    })

    it("envoie l'URL, la clé Bearer et le message utilisateur", async () => {
        const fetchImpl = vi.fn().mockResolvedValue(jsonResponse(okBody))
        await chatCompletion({ ...base, baseUrl: 'http://hermes:8642/v1', fetchImpl })
        const [url, init] = fetchImpl.mock.calls[0]
        expect(url).toBe('http://hermes:8642/v1/chat/completions')
        expect(init.headers.Authorization).toBe('Bearer secret-key')
        expect(init.headers['X-Hermes-Session-Id']).toBeUndefined()
        expect(JSON.parse(init.body)).toEqual({ model: 'hermes-agent', messages: [{ role: 'user', content: 'Bonjour' }], stream: false })
    })

    it('ajoute les instructions système et la session', async () => {
        const fetchImpl = vi.fn().mockResolvedValue(jsonResponse(okBody))
        await chatCompletion({ ...base, instructions: 'Sois bref', sessionId: ' s1 ', fetchImpl })
        const [, init] = fetchImpl.mock.calls[0]
        expect(init.headers['X-Hermes-Session-Id']).toBe('s1')
        expect(JSON.parse(init.body).messages).toEqual([
            { role: 'system', content: 'Sois bref' },
            { role: 'user', content: 'Bonjour' }
        ])
    })

    it('signale une clé refusée (401)', async () => {
        const fetchImpl = vi.fn().mockResolvedValue(jsonResponse({ error: 'bad key' }, 401))
        await failsWith(chatCompletion({ ...base, fetchImpl }), 'UNAUTHORIZED', /API_SERVER_KEY/)
    })

    it('signale trop de tâches simultanées (429)', async () => {
        const fetchImpl = vi.fn().mockResolvedValue(jsonResponse({ error: { message: 'too many' } }, 429))
        await failsWith(chatCompletion({ ...base, fetchImpl }), 'RATE_LIMITED', /too many/)
    })

    it('signale une indisponibilité (503)', async () => {
        const fetchImpl = vi.fn().mockResolvedValue(new Response('', { status: 503 }))
        await failsWith(chatCompletion({ ...base, fetchImpl }), 'UNAVAILABLE', /503/)
    })

    it('inclut le détail des autres erreurs HTTP', async () => {
        const fetchImpl = vi.fn().mockResolvedValue(jsonResponse({ error: { message: 'contenu non supporté' } }, 400))
        await failsWith(chatCompletion({ ...base, fetchImpl }), 'BAD_REQUEST', /400.*contenu non supporté/)
    })

    it('signale Hermes injoignable', async () => {
        const cause = Object.assign(new Error('connect'), { code: 'ECONNREFUSED' })
        const fetchImpl = vi.fn().mockRejectedValue(Object.assign(new TypeError('fetch failed'), { cause }))
        await failsWith(chatCompletion({ ...base, fetchImpl }), 'UNREACHABLE', /injoignable.*ECONNREFUSED.*docker compose ps/)
    })

    it('signale un dépassement de délai', async () => {
        // fetch qui ne répond jamais et respecte le signal d'annulation
        const fetchImpl = vi.fn(
            (_url: unknown, init: RequestInit) =>
                new Promise<Response>((_, reject) => {
                    init.signal!.addEventListener('abort', () => reject(Object.assign(new Error('aborted'), { name: 'AbortError' })))
                })
        )
        await failsWith(chatCompletion({ ...base, timeoutMs: 20, fetchImpl: fetchImpl as unknown as typeof fetch }), 'TIMEOUT', /n'a pas répondu/)
    })

    it('rejette une réponse sans contenu', async () => {
        const fetchImpl = vi.fn().mockResolvedValue(jsonResponse({ choices: [] }))
        await failsWith(chatCompletion({ ...base, fetchImpl }), 'BAD_RESPONSE', /inattendue/)
    })

    it('rejette une réponse vide', async () => {
        const fetchImpl = vi.fn().mockResolvedValue(jsonResponse({ choices: [{ message: { content: '  ' } }] }))
        await failsWith(chatCompletion({ ...base, fetchImpl }), 'BAD_RESPONSE', /vide/)
    })

    it('rejette un corps non JSON', async () => {
        const fetchImpl = vi.fn().mockResolvedValue(new Response('<html>', { status: 200 }))
        await failsWith(chatCompletion({ ...base, fetchImpl }), 'BAD_RESPONSE')
    })

    it("refuse une clé ou une URL vide sans appeler le réseau", async () => {
        const fetchImpl = vi.fn()
        await failsWith(chatCompletion({ ...base, apiKey: '', fetchImpl }), 'UNAUTHORIZED', /clé API/)
        await failsWith(chatCompletion({ ...base, baseUrl: ' ', fetchImpl }), 'BAD_REQUEST', /URL/)
        expect(fetchImpl).not.toHaveBeenCalled()
    })
})
