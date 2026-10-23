import { describe, it, expect, vi, beforeAll, beforeEach, afterEach } from 'vitest'
import { getCredentialData, getCredentialParam } from 'flowise-components'

// Les fichiers exportent via module.exports (convention Flowise) : selon le chargeur, l'export est à la racine ou sous « default ».
const load = async (path: string) => {
    const mod: any = await import(path)
    return mod.default ?? mod
}
let HermesTask: any
let HermesApi: any

beforeAll(async () => {
    HermesTask = (await load('../../src/nodes/agentflow/HermesTask/HermesTask')).nodeClass
    HermesApi = (await load('../../src/credentials/HermesApi.credential')).credClass
})

const okBody = { choices: [{ message: { content: 'Voici le résumé.', reasoning_content: 'raisonnement' } }], usage: { total_tokens: 5 } }

const makeNodeData = (inputs: Record<string, unknown>, credential: string | undefined = 'cred-1') => ({ id: 'hermesTaskAgentflow_0', inputs, credential })

beforeEach(() => {
    vi.mocked(getCredentialData).mockResolvedValue({ hermesBaseUrl: 'http://hermes:8642', hermesApiKey: 'k' })
    vi.mocked(getCredentialParam).mockImplementation((name: string, data: Record<string, unknown>) => data[name])
})
afterEach(() => vi.restoreAllMocks())

describe('credential HermesApi', () => {
    it("déclare l'URL et la clé (champ password)", () => {
        const cred = new HermesApi()
        expect(cred.name).toBe('hermesApi')
        expect(cred.inputs.map((i: any) => [i.name, i.type])).toEqual([
            ['hermesBaseUrl', 'string'],
            ['hermesApiKey', 'password']
        ])
    })
})

describe('nœud Hermes Task', () => {
    it('est un nœud Agentflow lié au credential hermesApi', () => {
        const node = new HermesTask()
        expect(node.category).toBe('Agent Flows')
        expect(node.credential.credentialNames).toEqual(['hermesApi'])
    })

    it('appelle Hermes et renvoie la sortie au format Agentflow', async () => {
        const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify(okBody), { status: 200 }))
        const state = { a: 1 }
        const out = await new HermesTask().run(makeNodeData({ hermesPrompt: 'Résume', hermesTimeout: 10 }), '', { agentflowRuntime: { state } })

        expect(fetchMock.mock.calls[0][0]).toBe('http://hermes:8642/v1/chat/completions')
        expect(out.output.content).toBe('Voici le résumé.')
        expect(out.state).toBe(state)
        expect(out.id).toBe('hermesTaskAgentflow_0')
        expect(JSON.stringify(out)).not.toContain('"k"') // la clé n'est jamais dans la sortie
    })

    it('refuse une tâche vide', async () => {
        await expect(new HermesTask().run(makeNodeData({ hermesPrompt: '  ' }), '', {})).rejects.toThrow(/« Tâche » est vide/)
    })

    it('exige un credential', async () => {
        await expect(new HermesTask().run(makeNodeData({ hermesPrompt: 'x' }, undefined), '', {})).rejects.toThrow(/credential/)
    })

    it("préfixe l'erreur Hermes pour l'interface Flowise (401)", async () => {
        vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('{}', { status: 401 }))
        await expect(new HermesTask().run(makeNodeData({ hermesPrompt: 'x' }), '', {})).rejects.toThrow(/^Hermes Task : Clé API refusée/)
    })

    it('utilise le délai par défaut si la valeur est invalide', async () => {
        const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify(okBody), { status: 200 }))
        await new HermesTask().run(makeNodeData({ hermesPrompt: 'x', hermesTimeout: 'abc' }), '', {})
        expect(fetchMock).toHaveBeenCalledOnce()
    })
})
