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
        expect(byName.hermesJobPrompt.show).toEqual({ hermesOperation: ['create', 'sync'] })
        expect(byName.hermesSyncRef.show).toEqual({ hermesOperation: ['sync'] })
        expect(byName.hermesJobRef.show.hermesOperation).toEqual(['get', 'delete', 'pause', 'resume', 'run'])
        expect(node.inputs[0].options.map((o: any) => o.name)).toEqual(['create', 'sync', 'get', 'list', 'pause', 'resume', 'run', 'delete'])
    })

    it('crée une tâche', async () => {
        const f = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(json({ jobs: [] })).mockResolvedValueOnce(json({ job }))
        const out = await run({ hermesOperation: 'create', hermesJobName: 'Digest', hermesJobSchedule: 'daily at 7am', hermesJobPrompt: 'Résume', hermesJobDeliver: 'telegram', hermesJobRepeat: '' })
        expect(JSON.parse((f.mock.calls[1][1] as RequestInit).body as string)).toMatchObject({ name: 'Digest', deliver: 'telegram' })
        expect(out.output.content).toMatch(/^Tâche planifiée créée : « Digest » \[abc123def456\]/)
        expect(out.output.job.id).toBe('abc123def456')
        expect(JSON.stringify(out)).not.toContain('"k"')
    })

    const definition = { hermesJobName: 'Limoges actus', hermesJobSchedule: '0 9 * * 1', hermesJobPrompt: 'Infos Limoges', hermesJobDeliver: 'local' }
    const limoges = { id: '2fe480e1937a', name: 'Limoges actus', schedule: { display: '0 9 * * 1' }, deliver: 'local', enabled: true, prompt: 'Infos Limoges' }

    it('« Créer » refuse un nom déjà pris et oriente vers « Synchroniser »', async () => {
        const f = vi.spyOn(globalThis, 'fetch').mockResolvedValue(json({ jobs: [limoges] }))
        await expect(run({ hermesOperation: 'create', ...definition })).rejects.toThrow(/existe déjà \[2fe480e1937a\].*Synchroniser/)
        expect(f).toHaveBeenCalledTimes(1) // aucune création
    })

    it('« Synchroniser » met à jour le job du même nom (sans doublon)', async () => {
        const f = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(json({ jobs: [limoges] })).mockResolvedValueOnce(json({ job: limoges }))
        const out = await run({ hermesOperation: 'sync', ...definition, hermesJobSchedule: 'every 2h' })
        const [url, init] = f.mock.calls[1] as [string, RequestInit]
        expect(url).toBe('http://hermes:8642/api/jobs/2fe480e1937a')
        expect(init.method).toBe('PATCH')
        expect(JSON.parse(init.body as string)).toMatchObject({ name: 'Limoges actus', schedule: 'every 2h' })
        expect(out.output.content).toMatch(/^Tâche planifiée mise à jour/)
    })

    it('« Synchroniser » crée le job s’il n’existe pas', async () => {
        const f = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(json({ jobs: [] })).mockResolvedValueOnce(json({ job: limoges }))
        const out = await run({ hermesOperation: 'sync', ...definition })
        expect((f.mock.calls[1][1] as RequestInit).method).toBe('POST')
        expect(out.output.content).toMatch(/^Tâche planifiée créée/)
    })

    it('« Synchroniser » avec un ID cible un job renommé côté Hermes', async () => {
        const renamed = { ...limoges, name: 'Autre nom' }
        const f = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(json({ jobs: [renamed] })).mockResolvedValueOnce(json({ job: limoges }))
        await run({ hermesOperation: 'sync', ...definition, hermesSyncRef: '2fe480e1937a' })
        expect(f.mock.calls[1][0]).toBe('http://hermes:8642/api/jobs/2fe480e1937a')
        expect(JSON.parse((f.mock.calls[1][1] as RequestInit).body as string).name).toBe('Limoges actus')
    })

    it('« Synchroniser » signale une cible introuvable plutôt que de créer un doublon', async () => {
        const f = vi.spyOn(globalThis, 'fetch').mockResolvedValue(json({ jobs: [limoges] }))
        await expect(run({ hermesOperation: 'sync', ...definition, hermesSyncRef: 'ffffffffffff' })).rejects.toThrow(/Aucune tâche planifiée « ffffffffffff »/)
        expect(f).toHaveBeenCalledTimes(1)
    })

    it('« Lire » renvoie la définition actuelle de Hermes, prompt compris', async () => {
        vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(json({ jobs: [limoges] })).mockResolvedValueOnce(json({ job: { ...limoges, schedule: { display: '0 9 * * 1' } } }))
        const out = await run({ hermesOperation: 'get', hermesJobRef: 'limoges actus' })
        expect(out.output.content).toContain('planning : 0 9 * * 1')
        expect(out.output.content).toContain('prompt : Infos Limoges')
        expect(out.output.job.id).toBe('2fe480e1937a')
    })

    it('liste (et gère le cas vide)', async () => {
        const f = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(json({ jobs: [job] })).mockResolvedValueOnce(json({ jobs: [] }))
        const listed = (await run({ hermesOperation: 'list' })).output.content
        expect(listed).toContain('« Digest »')
        expect(listed).not.toContain('prompt :') // la liste reste concise
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
