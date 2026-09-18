#!/usr/bin/env node
/**
 * Static checks that do not need a browser.
 *
 * The client half is a hand-written `__ModuleLoader__` bundle with no build
 * step, so the usual compiler safety net is absent. This script restores the
 * parts of it that matter: the factory must parse, the package manifest must
 * point at files that exist, every animation the client names must have an
 * asset, and the host half must import cleanly.
 */
import { readFileSync, existsSync, readdirSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const problems = []
const notes = []

const fail = (message) => problems.push(message)
const note = (message) => notes.push(message)

// --- 1. the client bundle must parse --------------------------------------
const clientPath = path.join(ROOT, 'lib', 'client.js')
const clientSource = readFileSync(clientPath, 'utf8')

const LOAD = 'window.__ModuleLoader__.load('
const start = clientSource.indexOf(LOAD)
if (start < 0) {
  fail('lib/client.js does not call window.__ModuleLoader__.load(')
} else {
  // Evaluate the loader call with a stub so the factory itself is constructed
  // and any syntax error surfaces here. The bundle is wrapped in a function so
  // it can run in a fresh context with a stub `window`.
  const body = clientSource.slice(start)
  const wrapped = `
    const fakeRequire = () => { throw new Error('require() called during check') };
    window.__ModuleLoader__.load = (spec) => {
      globalThis.__checked = { id: spec.id, exports: spec.factory(fakeRequire) };
    };
    ${body}
    globalThis.__checked = globalThis.__checked || null;
  `
  try {
    const vm = await import('node:vm')
    const sandbox = { console, globalThis: {} }
    sandbox.window = { __ModuleLoader__: {} }
    vm.runInNewContext(wrapped, sandbox, { filename: 'lib/client.js' })
    const checked = sandbox.globalThis.__checked
    if (!checked) fail('client factory did not register')
    else {
      for (const key of ['name', 'apply', 'inject']) {
        if (checked.exports?.[key] === undefined) fail(`client bundle does not export ${key}`)
      }
      note(`client bundle parsed: id=${checked.id}, exports=${Object.keys(checked.exports).join(', ')}`)
    }
  } catch (error) {
    fail(`lib/client.js factory failed to evaluate: ${error.message}`)
  }
}

// --- 2. package manifest integrity ----------------------------------------
const pkg = JSON.parse(readFileSync(path.join(ROOT, 'package.json'), 'utf8'))
for (const field of ['main', 'exports', 'files', 'dsh']) {
  if (!pkg[field]) fail(`package.json is missing "${field}"`)
}
const mainFile = path.join(ROOT, pkg.main ?? '')
if (!existsSync(mainFile)) fail(`package.json main does not exist: ${pkg.main}`)

const patchRel = pkg.dsh?.bundle?.patch
if (patchRel && !existsSync(path.join(ROOT, patchRel))) {
  fail(`dsh.bundle.patch does not exist: ${patchRel}`)
}
if (!pkg.exports?.['./client']) fail('package.json exports is missing "./client"')
else if (!existsSync(path.join(ROOT, pkg.exports['./client']))) {
  fail(`exports["./client"] does not exist: ${pkg.exports['./client']}`)
}

// --- 3. the host half must import ------------------------------------------
try {
  const { pathToFileURL } = await import('node:url')
  const host = await import(pathToFileURL(path.join(ROOT, 'lib', 'index.js')).href)
  if (typeof host.apply !== 'function') fail('host half does not export apply()')
  if (!Array.isArray(host.inject) || host.inject.length === 0) {
    fail('host half does not declare its inject list')
  }
  note(`host half imported: inject=${JSON.stringify(host.inject)}`)
} catch (error) {
  fail(`lib/index.js failed to import: ${error.message}`)
}

// --- 4. every animation the client names must exist ------------------------
const animDir = path.join(ROOT, 'assets', 'anims')
const present = existsSync(animDir)
  ? new Set(readdirSync(animDir).filter((f) => f.endsWith('.webm')).map((f) => path.basename(f, '.webm')))
  : new Set()

const animBlock = clientSource.match(/const ANIMS = \{([\s\S]*?)\n\t\t\};/)
if (!animBlock) fail('could not locate the ANIMS table in lib/client.js')
else {
  const named = [...animBlock[1].matchAll(/^\s{3}(\w+):\s*\{/gm)].map((m) => m[1])
  note(`client declares ${named.length} animations: ${named.join(', ')}`)
  const missing = named.filter((name) => !present.has(name))
  if (present.size === 0) note('no animation assets built yet (run `npm run art:build`)')
  else if (missing.length > 0) fail(`animations declared but not built: ${missing.join(', ')}`)
}

// --- 5. the voice directory must at least exist ----------------------------
if (!existsSync(path.join(ROOT, 'assets', 'voice'))) {
  note('assets/voice is absent (the pet will simply be silent)')
}

// --- report ---------------------------------------------------------------
for (const line of notes) console.log(`  · ${line}`)
if (problems.length === 0) {
  console.log('\nOK — package check passed')
} else {
  console.error('\nFAILED:')
  for (const line of problems) console.error(`  ✗ ${line}`)
  process.exitCode = 1
}
