import { describe, it, expect, vi, beforeAll, beforeEach, afterEach } from 'vitest'
import { getCredentialData, getCredentialParam } from 'flowise-components'

let HermesSchedule: any
beforeAll(async () => {
    const mod: any = await import('../../src/nodes/agentflow/HermesSchedule/HermesSchedule')
    HermesSchedule = (mod.default ?? mod).nodeClass
})

const job = { id: 'abc123def456', name: 'Digest', schedule: { display: 'daily at 7am' }, deliver: 'telegram', enabled: true }
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status })
const nodeData = (inputs: Record<string, unknown>, credential: string | undefined = 'c') => ({ id: 'hermesScheduleAgentflow_0', inputs, credential })
const run = (inputs: Record<string, unknown>, credential?: string) => new HermesSchedule().run(nodeData(inputs, credential), '', { agentflowRuntime: { state: {} } })

beforeEach(() => {
    vi.mocked(getCredentialData).mockResolvedValue({ hermesBaseUrl: 'http://hermes:8642', hermesApiKey: 'k' })
    vi.mocked(getCredentialParam).mockImplementation((name: string, data: Record<string, unknown>) => data[name])
})
afterEach(() => vi.restoreAllMocks())

describe('nœud Hermes Schedule', () => {
    it('affiche les champs selon l’opération', () => {
        const node = new HermesSchedule()
        const byName = Object.fromEntries(node.inputs.map((i: any) => [i.name, i]))
        expect(byName.hermesJobPrompt.show).toEqual({ hermesOperation: ['create'] })
        expect(byName.hermesJobRef.show.hermesOperation).toEqual(['delete', 'pause', 'resume', 'run'])
        expect(node.inputs[0].options.map((o: any) => o.name)).toEqual(['create', 'list', 'pause', 'resume', 'run', 'delete'])
    })

    it('crée une tâche', async () => {
        const f = vi.spyOn(globalThis, 'fetch').mockResolvedValue(json({ job }))
        const out = await run({ hermesOperation: 'create', hermesJobName: 'Digest', hermesJobSchedule: 'daily at 7am', hermesJobPrompt: 'Résume', hermesJobDeliver: 'telegram', hermesJobRepeat: '' })
        expect(JSON.parse((f.mock.calls[0][1] as RequestInit).body as string)).toMatchObject({ name: 'Digest', deliver: 'telegram' })
        expect(out.output.content).toMatch(/^Tâche planifiée créée : « Digest » \[abc123def456\]/)
        expect(out.output.job.id).toBe('abc123def456')
        expect(JSON.stringify(out)).not.toContain('"k"')
    })

    it('liste (et gère le cas vide)', async () => {
        const f = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(json({ jobs: [job] })).mockResolvedValueOnce(json({ jobs: [] }))
        expect((await run({ hermesOperation: 'list' })).output.content).toContain('« Digest »')
        expect((await run({ hermesOperation: 'list' })).output.content).toBe('Aucune tâche planifiée.')
        expect(f).toHaveBeenCalledTimes(2)
    })

    it.each([
        ['delete', 'supprimée'],
        ['pause', 'mise en pause'],
        ['resume', 'reprise'],
        ['run', 'déclenchée']
    ])('%s une tâche par son nom', async (operation, verb) => {
        const f = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(json({ jobs: [job] })).mockResolvedValueOnce(json(operation === 'delete' ? { ok: true } : { job }))
        const out = await run({ hermesOperation: operation, hermesJobRef: 'Digest' })
        expect(out.output.content).toBe(`Tâche abc123def456 ${verb}.`)
        expect(f).toHaveBeenCalledTimes(2)
    })

    it('exige un credential', async () => {
        await expect(run({ hermesOperation: 'list' }, undefined)).rejects.toThrow(/credential/)
    })

    it("préfixe les erreurs Hermes pour l'interface Flowise", async () => {
        vi.spyOn(globalThis, 'fetch').mockResolvedValue(json({ error: 'Invalid schedule "x"' }, 400))
        await expect(run({ hermesOperation: 'create', hermesJobName: 'n', hermesJobSchedule: 'x', hermesJobPrompt: 'p' })).rejects.toThrow(/^Hermes Schedule : .*Invalid schedule/)
    })

    it('signale Hermes injoignable', async () => {
        vi.spyOn(globalThis, 'fetch').mockRejectedValue(Object.assign(new TypeError('fetch failed'), { cause: { code: 'ECONNREFUSED' } }))
        await expect(run({ hermesOperation: 'list' })).rejects.toThrow(/^Hermes Schedule : Hermes est injoignable/)
    })
})
