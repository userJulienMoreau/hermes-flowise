import { ICommonObject, INode, INodeData, INodeParams, getCredentialData, getCredentialParam } from 'flowise-components'
import { HermesConnection, HermesError } from '../../shared/hermesClient'
import { createJob, describeJob, HermesJob, jobAction, JobAction, listJobs } from '../../shared/hermesJobs'

const DEFAULT_TIMEOUT_S = 30

type Operation = 'create' | 'list' | 'delete' | 'pause' | 'resume' | 'run'

const REF_OPERATIONS: Operation[] = ['delete', 'pause', 'resume', 'run']

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
                    { label: 'Créer', name: 'create' },
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
                show: { hermesOperation: ['create'] }
            },
            {
                label: 'Planning',
                name: 'hermesJobSchedule',
                type: 'string',
                acceptVariable: true,
                placeholder: 'daily at 7am  |  every 1h  |  0 9 * * MON-FRI',
                description: 'Formats Hermes : « every 2h », « daily at 7am », expression cron, « in 30m », date ISO.',
                show: { hermesOperation: ['create'] }
            },
            {
                label: 'Prompt de la tâche',
                name: 'hermesJobPrompt',
                type: 'string',
                rows: 4,
                acceptVariable: true,
                description: 'Instruction autonome exécutée par Hermes à chaque déclenchement (5000 caractères maximum).',
                show: { hermesOperation: ['create'] }
            },
            {
                label: 'Livraison',
                name: 'hermesJobDeliver',
                type: 'string',
                default: 'local',
                optional: true,
                placeholder: 'local | telegram | telegram:123456 | slack | all',
                description: 'Canal configuré dans Hermes. « local » enregistre seulement la sortie.',
                show: { hermesOperation: ['create'] }
            },
            {
                label: 'Nombre de répétitions',
                name: 'hermesJobRepeat',
                type: 'number',
                optional: true,
                description: 'Vide = illimité.',
                show: { hermesOperation: ['create'] }
            },
            {
                label: 'Tâche (ID ou nom)',
                name: 'hermesJobRef',
                type: 'string',
                acceptVariable: true,
                show: { hermesOperation: REF_OPERATIONS }
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
                case 'create': {
                    const repeatRaw = input.hermesJobRepeat
                    job = await createJob(conn, {
                        name: (input.hermesJobName as string) ?? '',
                        schedule: (input.hermesJobSchedule as string) ?? '',
                        prompt: (input.hermesJobPrompt as string) ?? '',
                        deliver: input.hermesJobDeliver as string | undefined,
                        repeat: repeatRaw === undefined || repeatRaw === null || repeatRaw === '' ? undefined : Number(repeatRaw)
                    })
                    content = `Tâche planifiée créée : ${describeJob(job)}`
                    break
                }
                case 'list': {
                    jobs = await listJobs(conn)
                    content = jobs.length ? jobs.map(describeJob).join('\n') : 'Aucune tâche planifiée.'
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
                input: { hermes: { operation, jobRef: input.hermesJobRef, name: input.hermesJobName, schedule: input.hermesJobSchedule, deliver: input.hermesJobDeliver } },
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
