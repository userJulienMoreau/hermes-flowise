import { INodeParams, INodeCredential } from 'flowise-components'

class HermesApi implements INodeCredential {
    label: string
    name: string
    version: number
    description: string
    inputs: INodeParams[]

    constructor() {
        this.label = 'Hermes API'
        this.name = 'hermesApi'
        this.version = 1.0
        this.description = "Accès au gateway Hermes Agent. La clé correspond à API_SERVER_KEY dans la configuration de Hermes."
        this.inputs = [
            {
                label: 'URL de Hermes',
                name: 'hermesBaseUrl',
                type: 'string',
                default: 'http://hermes:8642',
                placeholder: 'http://hermes:8642'
            },
            {
                label: 'Clé API (API_SERVER_KEY)',
                name: 'hermesApiKey',
                type: 'password'
            }
        ]
    }
}

module.exports = { credClass: HermesApi }
