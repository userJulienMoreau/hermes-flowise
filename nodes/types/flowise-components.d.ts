// Sous-ensemble des types de flowise-components 3.1.3 (packages/components/src/Interface.ts),
// pour compiler sans installer tout Flowise. Au runtime, le vrai module est utilisé.
declare module 'flowise-components' {
    export interface ICommonObject {
        [key: string]: any
    }

    export interface INodeParams {
        label: string
        name: string
        type: string
        default?: string | number | boolean | ICommonObject | ICommonObject[]
        description?: string
        credentialNames?: string[]
        optional?: boolean
        rows?: number
        step?: number
        placeholder?: string
        acceptVariable?: boolean
        additionalParams?: boolean
    }

    export interface INodeProperties {
        label: string
        name: string
        type: string
        icon: string
        version: number
        category: string
        baseClasses: string[]
        description?: string
        color?: string
        documentation?: string
        author?: string
    }

    export interface INode extends INodeProperties {
        credential?: INodeParams
        inputs?: INodeParams[]
        run?(nodeData: INodeData, input: string, options?: ICommonObject): Promise<string | ICommonObject>
    }

    export interface INodeData extends INodeProperties {
        id: string
        inputs?: ICommonObject
        credential?: string
    }

    export interface INodeCredential {
        label: string
        name: string
        description?: string
        inputs?: INodeParams[]
    }

    export function getCredentialData(selectedCredentialId: string, options: ICommonObject): Promise<ICommonObject>
    export function getCredentialParam(paramName: string, credentialData: ICommonObject, nodeData: INodeData, defaultValue?: any): any
}
