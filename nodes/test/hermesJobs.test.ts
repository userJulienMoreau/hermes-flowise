import { describe, it, expect, vi } from 'vitest'
import { HermesError } from '../src/nodes/shared/hermesClient'
import { createJob, describeJob, jobAction, listJobs, resolveJobId } from '../src/nodes/shared/hermesJobs'

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status })
const mk = (...responses: Response[]) => {
    const fn = vi.fn()
    responses.forEach((r) => fn.mockResolvedValueOnce(r))
    return fn
}
const conn = (fetchImpl: unknown) => ({ baseUrl: 'http://hermes:8642', apiKey: 'k', timeoutMs: 1000, fetchImpl: fetchImpl as typeof fetch })

const job = { id: 'abc123def456', name: 'Digest', schedule: { kind: 'cron', expr: '0 7 * * *', display: '0 7 * * *' }, deliver: 'telegram', enabled: true, next_run_at: '2026-10-24T07:00:00' }

const rejects = async (p: Promise<unknown>, code: string, pattern?: RegExp) => {
    const err = await p.then(() => null, (e) => e)
    expect(err).toBeInstanceOf(HermesError)
    expect(err.code).toBe(code)
    if (pattern) expect(err.message).toMatch(pattern)
}

describe('createJob', () => {
    it('envoie le bon corps vers POST /api/jobs', async () => {
        const f = mk(json({ job }))
        const res = await createJob(conn(f), { name: ' Digest ', schedule: 'daily at 7am', prompt: 'Résume', deliver: 'telegram', repeat: 3 })
        const [url, init] = f.mock.calls[0]
        expect(url).toBe('http://hermes:8642/api/jobs')
        expect(init.method).toBe('POST')
        expect(init.headers.Authorization).toBe('Bearer k')
        expect(JSON.parse(init.body)).toEqual({ name: 'Digest', schedule: 'daily at 7am', prompt: 'Résume', deliver: 'telegram', repeat: 3 })
        expect(res.id).toBe('abc123def456')
    })

    it('utilise « local » par défaut et omet repeat', async () => {
        const f = mk(json({ job }))
        await createJob(conn(f), { name: 'n', schedule: 's', prompt: 'p', deliver: '  ' })
        expect(JSON.parse(f.mock.calls[0][1].body)).toEqual({ name: 'n', schedule: 's', prompt: 'p', deliver: 'local' })
    })

    it.each([
        [{ name: '', schedule: 's', prompt: 'p' }, /nom/],
        [{ name: 'n', schedule: ' ', prompt: 'p' }, /planning/],
        [{ name: 'n', schedule: 's', prompt: ' ' }, /prompt/],
        [{ name: 'n'.repeat(201), schedule: 's', prompt: 'p' }, /200/],
        [{ name: 'n', schedule: 's', prompt: 'p'.repeat(5001) }, /5000/],
        [{ name: 'n', schedule: 's', prompt: 'p', repeat: 0 }, /entier positif/],
        [{ name: 'n', schedule: 's', prompt: 'p', repeat: 1.5 }, /entier positif/]
    ])('valide les entrées sans appeler Hermes (%#)', async (input, pattern) => {
        const f = vi.fn()
        await rejects(createJob(conn(f), input), 'BAD_REQUEST', pattern)
        expect(f).not.toHaveBeenCalled()
    })

    it("remonte l'erreur de validation de Hermes (planning invalide)", async () => {
        const f = mk(json({ error: 'Invalid schedule "blah"' }, 400))
        await rejects(createJob(conn(f), { name: 'n', schedule: 'blah', prompt: 'p' }), 'BAD_REQUEST', /Invalid schedule/)
    })

    it('rejette une réponse sans job', async () => {
        await rejects(createJob(conn(mk(json({}))), { name: 'n', schedule: 's', prompt: 'p' }), 'BAD_RESPONSE')
    })
})

describe('listJobs', () => {
    it('liste, y compris les jobs désactivés', async () => {
        const f = mk(json({ jobs: [job] }))
        expect(await listJobs(conn(f))).toEqual([job])
        expect(f.mock.calls[0][0]).toBe('http://hermes:8642/api/jobs?include_disabled=true')
        expect(f.mock.calls[0][1].method).toBe('GET')
    })

    it('rejette une réponse sans liste', async () => {
        await rejects(listJobs(conn(mk(json({})))), 'BAD_RESPONSE')
    })
})

describe('resolveJobId', () => {
    it('accepte un identifiant sans appeler Hermes', async () => {
        const f = vi.fn()
        expect(await resolveJobId(conn(f), ' abc123def456 ')).toBe('abc123def456')
        expect(f).not.toHaveBeenCalled()
    })

    it('résout un nom (insensible à la casse)', async () => {
        expect(await resolveJobId(conn(mk(json({ jobs: [job] }))), 'digest')).toBe('abc123def456')
    })

    it('signale un nom inconnu ou ambigu', async () => {
        await rejects(resolveJobId(conn(mk(json({ jobs: [job] }))), 'autre'), 'NOT_FOUND', /autre/)
        await rejects(resolveJobId(conn(mk(json({ jobs: [job, { ...job, id: '111111111111' }] }))), 'Digest'), 'BAD_REQUEST', /Plusieurs.*111111111111/)
    })

    it('refuse une référence vide', async () => {
        await rejects(resolveJobId(conn(vi.fn()), '  '), 'BAD_REQUEST')
    })
})

describe('jobAction', () => {
    it('supprime via DELETE', async () => {
        const f = mk(json({ ok: true }))
        expect(await jobAction(conn(f), 'delete', 'abc123def456')).toEqual({ id: 'abc123def456' })
        expect(f.mock.calls[0][0]).toBe('http://hermes:8642/api/jobs/abc123def456')
        expect(f.mock.calls[0][1].method).toBe('DELETE')
    })

    it.each(['pause', 'resume', 'run'] as const)('%s via POST', async (action) => {
        const f = mk(json({ job }))
        const res = await jobAction(conn(f), action, 'abc123def456')
        expect(f.mock.calls[0][0]).toBe(`http://hermes:8642/api/jobs/abc123def456/${action}`)
        expect(f.mock.calls[0][1].method).toBe('POST')
        expect(res.job?.id).toBe('abc123def456')
    })

    it('résout un nom avant d’agir', async () => {
        const f = mk(json({ jobs: [job] }), json({ ok: true }))
        await jobAction(conn(f), 'delete', 'Digest')
        expect(f.mock.calls[1][0]).toBe('http://hermes:8642/api/jobs/abc123def456')
    })

    it('signale un job introuvable (404)', async () => {
        await rejects(jobAction(conn(mk(json({ error: 'Job not found' }, 404))), 'delete', 'abc123def456'), 'NOT_FOUND', /Job not found/)
    })
})

describe('describeJob', () => {
    it('résume un job actif', () => {
        expect(describeJob(job)).toBe('« Digest » [abc123def456] · planning : 0 7 * * * · livraison : telegram · prochaine exécution : 2026-10-24T07:00:00')
    })
    it('indique la pause', () => {
        expect(describeJob({ ...job, enabled: false })).toContain('en pause')
    })
})
