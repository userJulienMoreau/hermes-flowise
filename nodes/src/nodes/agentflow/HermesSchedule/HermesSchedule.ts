import { ICommonObject, INode, INodeData, INodeParams, getCredentialData, getCredentialParam } from 'flowise-components'
import { HermesConnection, HermesError } from '../../shared/hermesClient'
import { createJob, describeJob, getJob, HermesJob, jobAction, JobAction, listJobs, syncJob } from '../../shared/hermesJobs'

const DEFAULT_TIMEOUT_S = 30

type Operation = 'create' | 'sync' | 'get' | 'list' | 'delete' | 'pause' | 'resume' | 'run'

const REF_OPERATIONS: Operation[] = ['get', 'delete', 'pause', 'resume', 'run']
const DEFINITION_OPERATIONS: Operation[] = ['create', 'sync']

class HermesSchedule_Agentflow implements INode {
    label: string
    name: string
    version: number
    description: string
    type: string
    icon: string
    category: string
    color: string
    baseClasses: string[]
    credential: INodeParams
    inputs: INodeParams[]

    constructor() {
        this.label = 'Hermes Schedule'
        this.name = 'hermesScheduleAgentflow'
        this.version = 1.0
        this.type = 'HermesSchedule'
        this.icon = 'hermes.svg'
        this.category = 'Agent Flows'
        this.description = 'Crée, liste, met en pause, relance ou supprime une tâche planifiée Hermes'
        this.baseClasses = [this.type]
        this.color = '#6C4BD6'
        this.credential = {
            label: 'Hermes API',
            name: 'credential',
            type: 'credential',
            credentialNames: ['hermesApi']
        }
        this.inputs = [
            {
                label: 'Opération',
                name: 'hermesOperation',
                type: 'options',
                options: [
                    { label: 'Créer (refuse si le nom existe déjà)', name: 'create' },
                    { label: 'Synchroniser (met à jour ou crée)', name: 'sync' },
                    { label: 'Lire (définition actuelle dans Hermes)', name: 'get' },
                    { label: 'Lister', name: 'list' },
                    { label: 'Mettre en pause', name: 'pause' },
                    { label: 'Reprendre', name: 'resume' },
                    { label: 'Exécuter maintenant', name: 'run' },
                    { label: 'Supprimer', name: 'delete' }
                ],
                default: 'create'
            },
            {
                label: 'Nom',
                name: 'hermesJobName',
                type: 'string',
                acceptVariable: true,
                show: { hermesOperation: DEFINITION_OPERATIONS }
            },
            {
                label: 'Planning',
                name: 'hermesJobSchedule',
                type: 'string',
                acceptVariable: true,
                placeholder: 'daily at 7am  |  every 1h  |  0 9 * * MON-FRI',
                description: 'Formats Hermes : « every 2h », « daily at 7am », expression cron, « in 30m », date ISO.',
                show: { hermesOperation: DEFINITION_OPERATIONS }
            },
            {
                label: 'Prompt de la tâche',
                name: 'hermesJobPrompt',
                type: 'string',
                rows: 4,
                acceptVariable: true,
                description: 'Instruction autonome exécutée par Hermes à chaque déclenchement (5000 caractères maximum).',
                show: { hermesOperation: DEFINITION_OPERATIONS }
            },
            {
                label: 'Livraison',
                name: 'hermesJobDeliver',
                type: 'string',
                default: 'local',
                optional: true,
                placeholder: 'local | telegram | telegram:123456 | slack | all',
                description: 'Canal configuré dans Hermes. « local » enregistre seulement la sortie.',
                show: { hermesOperation: DEFINITION_OPERATIONS }
            },
            {
                label: 'Nombre de répétitions',
                name: 'hermesJobRepeat',
                type: 'number',
                optional: true,
                description: 'Vide = illimité.',
                show: { hermesOperation: DEFINITION_OPERATIONS }
            },
            {
                label: 'Tâche (ID ou nom)',
                name: 'hermesJobRef',
                type: 'string',
                acceptVariable: true,
                show: { hermesOperation: REF_OPERATIONS }
            },
            {
                label: 'Tâche existante à mettre à jour (ID ou nom)',
                name: 'hermesSyncRef',
                type: 'string',
                acceptVariable: true,
                optional: true,
                description: 'Vide = le job du même nom. À renseigner pour renommer un job (ou si son nom a changé dans Hermes) sans en créer un second.',
                show: { hermesOperation: ['sync'] }
            },
            {
                label: 'Délai maximal (secondes)',
                name: 'hermesTimeout',
                type: 'number',
                default: DEFAULT_TIMEOUT_S,
                optional: true,
                additionalParams: true
            }
        ]
    }

    async run(nodeData: INodeData, _: string, options: ICommonObject): Promise<any> {
        const input = nodeData.inputs ?? {}
        const operation = (input.hermesOperation as Operation) ?? 'create'
        const timeoutS = Number(input.hermesTimeout) > 0 ? Number(input.hermesTimeout) : DEFAULT_TIMEOUT_S
        const state = options.agentflowRuntime?.state as ICommonObject

        if (!nodeData.credential) throw new Error('Hermes Schedule : sélectionnez un credential « Hermes API ».')
        const credentialData = await getCredentialData(nodeData.credential, options)
        const conn: HermesConnection = {
            baseUrl: getCredentialParam('hermesBaseUrl', credentialData, nodeData) as string,
            apiKey: getCredentialParam('hermesApiKey', credentialData, nodeData) as string,
            timeoutMs: timeoutS * 1000
        }

        try {
            let content: string
            let job: HermesJob | undefined
            let jobs: HermesJob[] | undefined

            switch (operation) {
                case 'create':
                case 'sync': {
                    const repeatRaw = input.hermesJobRepeat
                    const definition = {
                        name: (input.hermesJobName as string) ?? '',
                        schedule: (input.hermesJobSchedule as string) ?? '',
                        prompt: (input.hermesJobPrompt as string) ?? '',
                        deliver: input.hermesJobDeliver as string | undefined,
                        repeat: repeatRaw === undefined || repeatRaw === null || repeatRaw === '' ? undefined : Number(repeatRaw)
                    }
                    if (operation === 'create') {
                        const existing = (await listJobs(conn)).find((j) => j.name?.toLowerCase() === definition.name.trim().toLowerCase())
                        if (existing) {
                            throw new HermesError(
                                `Une tâche nommée « ${definition.name.trim()} » existe déjà [${existing.id}] : utilisez l'opération « Synchroniser » pour la mettre à jour.`,
                                'BAD_REQUEST'
                            )
                        }
                        job = await createJob(conn, definition)
                        content = `Tâche planifiée créée : ${describeJob(job)}`
                    } else {
                        const res = await syncJob(conn, definition, input.hermesSyncRef as string | undefined)
                        job = res.job
                        content = `Tâche planifiée ${res.action === 'created' ? 'créée' : 'mise à jour'} : ${describeJob(job)}`
                    }
                    break
                }
                case 'get': {
                    job = await getJob(conn, (input.hermesJobRef as string) ?? '')
                    content = describeJob(job, true)
                    break
                }
                case 'list': {
                    jobs = await listJobs(conn)
                    content = jobs.length ? jobs.map((j) => describeJob(j)).join('\n') : 'Aucune tâche planifiée.'
                    break
                }
                case 'delete':
                case 'pause':
                case 'resume':
                case 'run': {
                    const res = await jobAction(conn, operation as JobAction, (input.hermesJobRef as string) ?? '')
                    job = res.job ?? { id: res.id }
                    const verbs = { delete: 'supprimée', pause: 'mise en pause', resume: 'reprise', run: 'déclenchée' }
                    content = `Tâche ${res.id} ${verbs[operation]}.`
                    break
                }
                default:
                    throw new HermesError(`Opération inconnue : ${operation}`, 'BAD_REQUEST')
            }

            return {
                id: nodeData.id,
                name: this.name,
                input: { hermes: { operation, jobRef: input.hermesJobRef, syncRef: input.hermesSyncRef, name: input.hermesJobName, schedule: input.hermesJobSchedule, deliver: input.hermesJobDeliver } },
                output: { content, job, jobs },
                state
            }
        } catch (e) {
            if (e instanceof HermesError) throw new Error(`Hermes Schedule : ${e.message}`)
            throw e
        }
    }
}

module.exports = { nodeClass: HermesSchedule_Agentflow }
