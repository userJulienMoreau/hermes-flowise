/**
 * Gestion des tâches planifiées de Hermes via l'API du gateway (GET/POST /api/jobs, /api/jobs/{id}/...).
 * Contraintes lues dans gateway/platforms/api_server.py : nom ≤ 200 caractères, prompt ≤ 5000,
 * identifiant = 12 caractères hexadécimaux.
 */
import { HermesConnection, HermesError, hermesRequest } from './hermesClient'

export const MAX_NAME_LENGTH = 200
export const MAX_PROMPT_LENGTH = 5000

export interface HermesJob {
    id: string
    name?: string
    prompt?: string
    schedule?: { kind?: string; expr?: string; display?: string } | string
    deliver?: string
    enabled?: boolean
    state?: string
    next_run_at?: string | null
    last_run_at?: string | null
    last_status?: string | null
    [key: string]: unknown
}

export interface CreateJobInput {
    name: string
    schedule: string
    prompt: string
    /** Cible de livraison : local, telegram, telegram:<chat_id>, slack, all… (défaut côté Hermes : local). */
    deliver?: string
    /** Nombre d'exécutions avant arrêt (vide = illimité). */
    repeat?: number
}

const JOB_ID_RE = /^[a-f0-9]{12}$/

export const createJob = async (conn: HermesConnection, input: CreateJobInput): Promise<HermesJob> => {
    const name = input.name?.trim()
    const schedule = input.schedule?.trim()
    if (!name) throw new HermesError('Le nom de la tâche planifiée est obligatoire.', 'BAD_REQUEST')
    if (name.length > MAX_NAME_LENGTH) throw new HermesError(`Le nom dépasse ${MAX_NAME_LENGTH} caractères.`, 'BAD_REQUEST')
    if (!schedule) throw new HermesError('Le planning est obligatoire (ex. « daily at 7am », « every 1h » ou « 0 9 * * MON-FRI »).', 'BAD_REQUEST')
    if (!input.prompt?.trim()) throw new HermesError('Le prompt de la tâche planifiée est obligatoire.', 'BAD_REQUEST')
    if (input.prompt.length > MAX_PROMPT_LENGTH) throw new HermesError(`Le prompt dépasse ${MAX_PROMPT_LENGTH} caractères (limite de Hermes).`, 'BAD_REQUEST')
    if (input.repeat !== undefined && (!Number.isInteger(input.repeat) || input.repeat < 1)) {
        throw new HermesError('Le nombre de répétitions doit être un entier positif.', 'BAD_REQUEST')
    }

    const body: Record<string, unknown> = { name, schedule, prompt: input.prompt, deliver: input.deliver?.trim() || 'local' }
    if (input.repeat !== undefined) body.repeat = input.repeat

    const res = await hermesRequest({ ...conn, method: 'POST', path: '/api/jobs', body })
    if (!res?.job?.id) throw new HermesError('Réponse inattendue de Hermes : pas de job dans la réponse.', 'BAD_RESPONSE')
    return res.job
}

export const listJobs = async (conn: HermesConnection, includeDisabled = true): Promise<HermesJob[]> => {
    const res = await hermesRequest({ ...conn, method: 'GET', path: `/api/jobs${includeDisabled ? '?include_disabled=true' : ''}` })
    if (!Array.isArray(res?.jobs)) throw new HermesError('Réponse inattendue de Hermes : liste de jobs absente.', 'BAD_RESPONSE')
    return res.jobs
}

/** Accepte un identifiant (12 hex) ou un nom de job (insensible à la casse, comme la CLI hermes cron). */
export const resolveJobId = async (conn: HermesConnection, ref: string): Promise<string> => {
    const value = ref?.trim()
    if (!value) throw new HermesError("Indiquez l'identifiant ou le nom de la tâche planifiée.", 'BAD_REQUEST')
    if (JOB_ID_RE.test(value)) return value

    const matches = (await listJobs(conn)).filter((j) => j.name?.toLowerCase() === value.toLowerCase())
    if (matches.length === 0) throw new HermesError(`Aucune tâche planifiée nommée « ${value} » (utilisez l'opération « Lister »).`, 'NOT_FOUND')
    if (matches.length > 1) {
        throw new HermesError(`Plusieurs tâches portent le nom « ${value} » (${matches.map((j) => j.id).join(', ')}) : utilisez l'identifiant.`, 'BAD_REQUEST')
    }
    return matches[0].id
}

export type JobAction = 'delete' | 'pause' | 'resume' | 'run'

export const jobAction = async (conn: HermesConnection, action: JobAction, ref: string): Promise<{ id: string; job?: HermesJob }> => {
    const id = await resolveJobId(conn, ref)
    if (action === 'delete') {
        await hermesRequest({ ...conn, method: 'DELETE', path: `/api/jobs/${id}` })
        return { id }
    }
    const res = await hermesRequest({ ...conn, method: 'POST', path: `/api/jobs/${id}/${action}` })
    return { id, job: res?.job }
}

const scheduleLabel = (job: HermesJob): string => {
    const s = job.schedule
    if (typeof s === 'string') return s
    return s?.display ?? s?.expr ?? '?'
}

/** Résumé lisible d'un job, pour la sortie texte du nœud. */
export const describeJob = (job: HermesJob): string => {
    const parts = [`« ${job.name ?? '(sans nom)'} » [${job.id}]`, `planning : ${scheduleLabel(job)}`, `livraison : ${job.deliver ?? 'local'}`]
    if (job.enabled === false || job.state === 'paused') parts.push('en pause')
    else if (job.next_run_at) parts.push(`prochaine exécution : ${job.next_run_at}`)
    if (job.last_status) parts.push(`dernier statut : ${job.last_status}`)
    return parts.join(' · ')
}
