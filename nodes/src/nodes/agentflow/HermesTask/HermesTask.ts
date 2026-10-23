import { ICommonObject, INode, INodeData, INodeParams, getCredentialData, getCredentialParam } from 'flowise-components'
import { chatCompletion, HermesError } from '../../shared/hermesClient'

const DEFAULT_TIMEOUT_S = 300

class HermesTask_Agentflow implements INode {
    label: string
    name: string
    version: number
    description: string
    type: string
    icon: string
    category: string
    color: string
    baseClasses: string[]
    documentation?: string
    credential: INodeParams
    inputs: INodeParams[]

    constructor() {
        this.label = 'Hermes Task'
        this.name = 'hermesTaskAgentflow'
        this.version = 1.0
        this.type = 'HermesTask'
        this.icon = 'hermes.svg'
        this.category = 'Agent Flows'
        this.description = 'Envoie une tâche à Hermes Agent et renvoie sa réponse'
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
                label: 'Tâche',
                name: 'hermesPrompt',
                type: 'string',
                rows: 4,
                acceptVariable: true,
                placeholder: 'Résume les actualités du jour sur {{ question }}'
            },
            {
                label: 'Instructions (système)',
                name: 'hermesInstructions',
                type: 'string',
                rows: 3,
                acceptVariable: true,
                optional: true,
                additionalParams: true
            },
            {
                label: 'ID de session',
                name: 'hermesSessionId',
                type: 'string',
                acceptVariable: true,
                optional: true,
                additionalParams: true,
                description: 'Envoyé dans X-Hermes-Session-Id pour réutiliser une session Hermes.'
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
        const prompt = ((nodeData.inputs?.hermesPrompt as string) ?? '').trim()
        const instructions = nodeData.inputs?.hermesInstructions as string | undefined
        const sessionId = nodeData.inputs?.hermesSessionId as string | undefined
        const timeoutS = Number(nodeData.inputs?.hermesTimeout) > 0 ? Number(nodeData.inputs?.hermesTimeout) : DEFAULT_TIMEOUT_S

        const state = options.agentflowRuntime?.state as ICommonObject

        if (!prompt) throw new Error('Hermes Task : le champ « Tâche » est vide.')
        if (!nodeData.credential) throw new Error('Hermes Task : sélectionnez un credential « Hermes API ».')

        const credentialData = await getCredentialData(nodeData.credential, options)
        const baseUrl = getCredentialParam('hermesBaseUrl', credentialData, nodeData) as string
        const apiKey = getCredentialParam('hermesApiKey', credentialData, nodeData) as string

        try {
            const result = await chatCompletion({ baseUrl, apiKey, prompt, instructions, sessionId, timeoutMs: timeoutS * 1000 })
            return {
                id: nodeData.id,
                name: this.name,
                input: { hermes: { prompt, instructions, sessionId, timeoutS } },
                output: { content: result.content, reasoning: result.reasoning, usage: result.usage },
                state
            }
        } catch (e) {
            // Le message affiché dans l'interface Flowise est celui de l'exception.
            if (e instanceof HermesError) throw new Error(`Hermes Task : ${e.message}`)
            throw e
        }
    }
}

module.exports = { nodeClass: HermesTask_Agentflow }
