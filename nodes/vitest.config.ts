import { defineConfig } from 'vitest/config'
import path from 'path'

export default defineConfig({
    test: { include: ['test/**/*.test.ts'] },
    resolve: {
        // flowise-components n'est présent que dans l'image Flowise : on le remplace par un stub.
        alias: { 'flowise-components': path.resolve(__dirname, 'test/stubs/flowise-components.ts') }
    }
})
