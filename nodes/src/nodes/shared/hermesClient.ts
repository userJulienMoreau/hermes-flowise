/**
 * Client HTTP minimal pour l'API OpenAI-compatible du gateway Hermes.
 * Aucune dépendance à Flowise : toute la logique d'appel et de gestion d'erreurs est testable seule.
 */

export class HermesError extends Error {
    constructor(
        message: string,
        public readonly code: 'UNREACHABLE' | 'TIMEOUT' | 'UNAUTHORIZED' | 'RATE_LIMITED' | 'UNAVAILABLE' | 'BAD_REQUEST' | 'BAD_RESPONSE',
        public readonly status?: number
    ) {
        super(message)
        this.name = 'HermesError'
    }
}

export interface HermesChatOptions {
    baseUrl: string
    apiKey: string
    prompt: string
    instructions?: string
    sessionId?: string
    /** Délai maximal en millisecondes. */
    timeoutMs: number
    fetchImpl?: typeof fetch
}

export interface HermesChatResult {
    content: string
    reasoning?: string
    usage?: Record<string, number>
}

/** Retire les espaces, le « / » final et un éventuel « /v1 » final : on ajoute nous-mêmes le chemin. */
export const normalizeBaseUrl = (baseUrl: string): string => baseUrl.trim().replace(/\/+$/, '').replace(/\/v1$/, '')

const extractApiMessage = (body: any): string | undefined => {
    const err = body?.error
    if (typeof err === 'string') return err
    if (typeof err?.message === 'string') return err.message
    if (typeof body?.message === 'string') return body.message
    return undefined
}

export const chatCompletion = async (opts: HermesChatOptions): Promise<HermesChatResult> => {
    const baseUrl = normalizeBaseUrl(opts.baseUrl)
    if (!baseUrl) throw new HermesError("L'URL de Hermes est vide : renseignez-la dans le credential « Hermes API ».", 'BAD_REQUEST')
    if (!opts.apiKey) throw new HermesError("La clé API de Hermes est vide : renseignez-la dans le credential « Hermes API ».", 'UNAUTHORIZED')

    const messages: { role: string; content: string }[] = []
    if (opts.instructions?.trim()) messages.push({ role: 'system', content: opts.instructions })
    messages.push({ role: 'user', content: opts.prompt })

    const headers: Record<string, string> = {
        Authorization: `Bearer ${opts.apiKey}`,
        'Content-Type': 'application/json'
    }
    if (opts.sessionId?.trim()) headers['X-Hermes-Session-Id'] = opts.sessionId.trim()

    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), opts.timeoutMs)
    const doFetch = opts.fetchImpl ?? fetch

    let response: Response
    try {
        response = await doFetch(`${baseUrl}/v1/chat/completions`, {
            method: 'POST',
            headers,
            body: JSON.stringify({ model: 'hermes-agent', messages, stream: false }),
            signal: controller.signal
        })
    } catch (e: any) {
        clearTimeout(timer)
        if (controller.signal.aborted || e?.name === 'AbortError') {
            throw new HermesError(
                `Hermes n'a pas répondu en ${Math.round(opts.timeoutMs / 1000)} s. Augmentez le délai du nœud ou simplifiez la tâche.`,
                'TIMEOUT'
            )
        }
        throw new HermesError(
            `Hermes est injoignable à l'adresse ${baseUrl} (${e?.cause?.code ?? e?.message ?? 'erreur réseau'}). ` +
                'Vérifiez que le service tourne (docker compose ps) et que l’URL du credential est correcte.',
            'UNREACHABLE'
        )
    }

    // Le corps (non-streaming) peut aussi être long à arriver : le délai court jusqu'à la fin de la lecture.
    let text: string
    try {
        text = await response.text()
    } catch (e: any) {
        throw new HermesError(
            controller.signal.aborted ? `Hermes n'a pas terminé sa réponse en ${Math.round(opts.timeoutMs / 1000)} s.` : `Lecture de la réponse de Hermes interrompue : ${e?.message}`,
            controller.signal.aborted ? 'TIMEOUT' : 'BAD_RESPONSE'
        )
    } finally {
        clearTimeout(timer)
    }

    let body: any
    try {
        body = text ? JSON.parse(text) : undefined
    } catch {
        body = undefined
    }

    if (!response.ok) {
        const detail = extractApiMessage(body)
        const suffix = detail ? ` Détail : ${detail}` : ''
        switch (response.status) {
            case 401:
            case 403:
                throw new HermesError('Clé API refusée par Hermes (HTTP ' + response.status + '). Vérifiez que la clé du credential égale API_SERVER_KEY.', 'UNAUTHORIZED', response.status)
            case 429:
                throw new HermesError('Hermes a atteint son nombre maximal de tâches simultanées (HTTP 429). Réessayez dans un instant.' + suffix, 'RATE_LIMITED', 429)
            case 503:
                throw new HermesError('Hermes est momentanément indisponible (HTTP 503, redémarrage ou base verrouillée). Réessayez.' + suffix, 'UNAVAILABLE', 503)
            default:
                throw new HermesError(`Hermes a répondu une erreur HTTP ${response.status}.${suffix}`, response.status >= 500 ? 'UNAVAILABLE' : 'BAD_REQUEST', response.status)
        }
    }

    const message = body?.choices?.[0]?.message
    if (!message || typeof message.content !== 'string') {
        throw new HermesError('Réponse inattendue de Hermes : pas de contenu dans choices[0].message.', 'BAD_RESPONSE', response.status)
    }
    if (!message.content.trim()) {
        throw new HermesError("Hermes a renvoyé une réponse vide.", 'BAD_RESPONSE', response.status)
    }

    return {
        content: message.content,
        reasoning: typeof message.reasoning_content === 'string' ? message.reasoning_content : undefined,
        usage: body.usage
    }
}
