// Copie les icônes à côté des .js compilés (Flowise les sert depuis le dossier du nœud).
const fs = require('fs')
const path = require('path')

const walk = (dir) =>
    fs.readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
        const p = path.join(dir, e.name)
        return e.isDirectory() ? walk(p) : [p]
    })

for (const file of walk(path.join(__dirname, '..', 'src')).filter((f) => f.endsWith('.svg'))) {
    const dest = path.join(__dirname, '..', 'build', path.relative(path.join(__dirname, '..', 'src'), file))
    fs.mkdirSync(path.dirname(dest), { recursive: true })
    fs.copyFileSync(file, dest)
}
