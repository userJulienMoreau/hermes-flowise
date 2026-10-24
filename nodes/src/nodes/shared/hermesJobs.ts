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

const validateJobInput = (input: CreateJobInput): { name: string; schedule: string } => {
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
    return { name, schedule }
}

const jobBody = (input: CreateJobInput, name: string, schedule: string): Record<string, unknown> => {
    const body: Record<string, unknown> = { name, schedule, prompt: input.prompt, deliver: input.deliver?.trim() || 'local' }
    if (input.repeat !== undefined) body.repeat = input.repeat
    return body
}

export const createJob = async (conn: HermesConnection, input: CreateJobInput): Promise<HermesJob> => {
    const { name, schedule } = validateJobInput(input)
    const body = jobBody(input, name, schedule)

    const res = await hermesRequest({ ...conn, method: 'POST', path: '/api/jobs', body })
    if (!res?.job?.id) throw new HermesError('Réponse inattendue de Hermes : pas de job dans la réponse.', 'BAD_RESPONSE')
    return res.job
}

export type SyncResult = { action: 'created' | 'updated'; job: HermesJob }

/**
 * Fait correspondre un job Hermes à une définition (nom, planning, prompt, livraison) :
 *  - `ref` (ID ou nom) renseigné : ce job est mis à jour (renommage possible) ; introuvable = erreur ;
 *  - sinon le job du même nom est mis à jour, et à défaut un job est créé.
 * Rejouer le flow ne crée donc jamais de doublon. Hermes conserve les champs non fournis (ex. `repeat`).
 */
export const syncJob = async (conn: HermesConnection, input: CreateJobInput, ref?: string): Promise<SyncResult> => {
    const { name, schedule } = validateJobInput(input)
    const target = ref?.trim() || name

    const jobs = await listJobs(conn)
    const lower = target.toLowerCase()
    const matches = jobs.filter((j) => j.id === target || j.name?.toLowerCase() === lower)
    if (matches.length > 1) {
        throw new HermesError(`Plusieurs tâches correspondent à « ${target} » (${matches.map((j) => j.id).join(', ')}) : indiquez l'identifiant du job.`, 'BAD_REQUEST')
    }
    if (matches.length === 0) {
        if (ref?.trim()) throw new HermesError(`Aucune tâche planifiée « ${ref.trim()} » à mettre à jour (laissez le champ vide pour la créer).`, 'NOT_FOUND')
        return { action: 'created', job: await createJob(conn, input) }
    }

    const body = jobBody(input, name, schedule)
    const res = await hermesRequest({ ...conn, method: 'PATCH', path: `/api/jobs/${matches[0].id}`, body })
    if (!res?.job?.id) throw new HermesError('Réponse inattendue de Hermes : pas de job dans la réponse.', 'BAD_RESPONSE')
    return { action: 'updated', job: res.job }
}

/** Définition actuelle d'un job (source de vérité : Hermes). */
export const getJob = async (conn: HermesConnection, ref: string): Promise<HermesJob> => {
    const id = await resolveJobId(conn, ref)
    const res = await hermesRequest({ ...conn, method: 'GET', path: `/api/jobs/${id}` })
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
export const describeJob = (job: HermesJob, withPrompt = false): string => {
    const parts = [`« ${job.name ?? '(sans nom)'} » [${job.id}]`, `planning : ${scheduleLabel(job)}`, `livraison : ${job.deliver ?? 'local'}`]
    if (job.enabled === false || job.state === 'paused') parts.push('en pause')
    else if (job.next_run_at) parts.push(`prochaine exécution : ${job.next_run_at}`)
    if (job.last_status) parts.push(`dernier statut : ${job.last_status}`)
    if (withPrompt && job.prompt) parts.push(`prompt : ${job.prompt}`)
    return parts.join(' · ')
}
