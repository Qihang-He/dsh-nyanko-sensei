/**
 * dsh-nyanko-sensei — host half.
 *
 * The pet itself runs entirely in the browser (see `./client`); this half does
 * the two things a page cannot do for itself:
 *
 * 1. **Serve the pet's media.** Animation frames (VP9-alpha WebM) and voice
 *    clips are far too large to inline into a client bundle, so they ship as
 *    package assets behind one prefix route. Two roots are mounted under the
 *    same path: the read-only assets inside the package, and a user root under
 *    `$DSH_HOME/dsh-nyanko-sensei/` that can override them — which is how a
 *    user drops in their own voice recordings without touching the package.
 * 2. **Publish the media manifest.** The browser half asks for
 *    `/dsh-nyanko-sensei/manifest.json` once at startup and learns which
 *    animations and which voice packs exist, instead of guessing at file names.
 *
 * Nothing here is required for the pet to render: if the route cannot be
 * registered the browser half falls back to its built-in asset list and simply
 * has no user voice pack.
 *
 * @module dsh-nyanko-sensei
 */

import { createReadStream } from 'node:fs'
import { readdir, readFile, stat } from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

/** Required service: the HTTP route registry the media is served from. */
export const inject = ['webServer']

const NS = 'dsh-nyanko-sensei'

/** URL prefix owned by this plugin. */
const ROUTE = `/${NS}`

/** Package root (`lib/` sits one level below it). */
const PKG_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')

/** Read-only media shipped with the package. */
const BUILTIN_ROOT = path.join(PKG_ROOT, 'assets')

/**
 * User media root. Anything placed here wins over the packaged file of the same
 * relative path, so a user recording of a voice line needs no rebuild and no
 * edits to the package.
 */
function userRoot() {
  const home = process.env.DSH_HOME ?? path.join(os.homedir(), '.dsh')
  return path.join(home, NS)
}

/** Media types for the extensions the pet actually uses. */
const MIME = {
  '.webm': 'video/webm',
  '.mp4': 'video/mp4',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.webp': 'image/webp',
  '.gif': 'image/gif',
  '.mp3': 'audio/mpeg',
  '.m4a': 'audio/mp4',
  '.aac': 'audio/aac',
  '.ogg': 'audio/ogg',
  '.oga': 'audio/ogg',
  '.opus': 'audio/ogg',
  '.wav': 'audio/wav',
  '.flac': 'audio/flac',
  '.json': 'application/json; charset=utf-8',
  '.txt': 'text/plain; charset=utf-8',
  '.md': 'text/markdown; charset=utf-8',
}

/** Extensions a request is allowed to name. Keeps the route a closed set. */
const ALLOWED_EXT = new Set(Object.keys(MIME))

/** Audio extensions recognised as voice clips, in preference order. */
const AUDIO_EXT = ['.mp3', '.m4a', '.aac', '.ogg', '.oga', '.opus', '.wav', '.flac']

/** Animation extensions recognised, in preference order. */
const VIDEO_EXT = ['.webm', '.mp4']

/**
 * Resolve a request path under the media roots.
 *
 * The path is refused unless it is relative, normalises to something that stays
 * inside a root, and ends in an extension from the allow-list. This is the only
 * place a URL reaches the filesystem, so the containment check lives here and
 * is deliberately paranoid (separator, `..` and absolute-path rejection, then a
 * final `path.relative` containment assertion).
 *
 * @param rel - the decoded relative path from the URL.
 * @returns the absolute candidate paths, user root first.
 */
function candidates(rel) {
  if (typeof rel !== 'string' || rel === '') return []
  if (rel.includes('\0') || rel.includes('\\')) return []
  if (path.isAbsolute(rel) || rel.split('/').includes('..')) return []
  const ext = path.extname(rel).toLowerCase()
  if (!ALLOWED_EXT.has(ext)) return []

  const cleaned = path.normalize(rel)
  const roots = [userRoot(), BUILTIN_ROOT]
  const out = []
  for (const root of roots) {
    const abs = path.join(root, cleaned)
    const relative = path.relative(root, abs)
    if (relative === '' || relative.startsWith('..') || path.isAbsolute(relative)) continue
    out.push(abs)
  }
  return out
}

/** First existing regular file among the candidates, or undefined. */
async function firstFile(paths) {
  for (const candidate of paths) {
    try {
      const info = await stat(candidate)
      if (info.isFile()) return { abs: candidate, size: info.size }
    } catch {
      // Missing candidate: try the next root.
    }
  }
  return undefined
}

/** List the files directly inside a directory, never throwing on a missing one. */
async function listDir(dir) {
  try {
    return await readdir(dir, { withFileTypes: true })
  } catch {
    return []
  }
}

/**
 * Collect the animation names available across both roots.
 *
 * A name is the file stem, so `assets/anims/idle.webm` is the `idle` animation.
 * user-root files shadow built-in ones with the same stem, and the built-in
 * order from the package is preserved rather than resorted, so the client's
 * default action pools stay in the authored order.
 *
 * @returns sorted animation names.
 */
async function collectAnims() {
  const names = new Set()
  for (const root of [BUILTIN_ROOT, userRoot()]) {
    for (const entry of await listDir(path.join(root, 'anims'))) {
      if (!entry.isFile()) continue
      const ext = path.extname(entry.name).toLowerCase()
      if (!VIDEO_EXT.includes(ext)) continue
      names.add(path.basename(entry.name, ext))
    }
  }
  return [...names].sort()
}

/**
 * Collect voice packs.
 *
 * A pack is either the built-in `assets/voice/` directory itself (exposed as the
 * pack named `default`) or any subdirectory of a `voice/` root. Clips are the
 * audio files directly inside a pack; the clip name is the file stem, so the
 * client can ask for `natsume` and get whichever format the user supplied.
 *
 * @returns `{ packs: [{id, clips: [{id, ext, bytes}]}] }`.
 */
async function collectVoice() {
  /** @type {Map<string, Map<string, {id: string, ext: string, bytes: number}>>} */
  const packs = new Map()
  const addPack = (id) => {
    if (!packs.has(id)) packs.set(id, new Map())
    return packs.get(id)
  }

  /** Add every audio file directly inside `dir` to pack `id`. */
  const scanPack = async (id, dir) => {
    const clips = addPack(id)
    for (const entry of await listDir(dir)) {
      if (!entry.isFile()) continue
      const ext = path.extname(entry.name).toLowerCase()
      if (!AUDIO_EXT.includes(ext)) continue
      const clipId = path.basename(entry.name, ext)
      if (clips.has(clipId)) continue // first extension in AUDIO_EXT order wins
      const info = await stat(path.join(dir, entry.name))
      clips.set(clipId, { id: clipId, ext, bytes: info.size })
    }
  }

  for (const root of [BUILTIN_ROOT, userRoot()]) {
    const voiceDir = path.join(root, 'voice')
    await scanPack('default', voiceDir)
    for (const entry of await listDir(voiceDir)) {
      if (!entry.isDirectory()) continue
      await scanPack(entry.name, path.join(voiceDir, entry.name))
    }
  }

  return {
    packs: [...packs.entries()]
      .map(([id, clips]) => ({ id, clips: [...clips.values()].sort((a, b) => a.id.localeCompare(b.id)) }))
      .filter((pack) => pack.clips.length > 0)
      .sort((a, b) => (a.id === 'default' ? -1 : b.id === 'default' ? 1 : a.id.localeCompare(b.id))),
  }
}

/** The manifest the browser half reads once at startup. */
async function buildManifest() {
  const [anims, voice, version] = await Promise.all([
    collectAnims(),
    collectVoice(),
    readVersion(),
  ])
  return {
    ok: true,
    name: NS,
    version,
    route: ROUTE,
    anims,
    voice: voice.packs,
    userRoot: userRoot(),
  }
}

/**
 * Package version, read from the manifest next to this file.
 *
 * Deliberately not `process.env.npm_package_version`: that is only set when the
 * package is started by npm, so a plugin loaded by the host reported `0.0.0`.
 * Never throws — a missing or unreadable manifest must not stop the media route
 * from mounting.
 */
async function readVersion() {
  try {
    const raw = await readFile(path.join(PKG_ROOT, 'package.json'), 'utf8')
    return JSON.parse(raw).version ?? '0.0.0'
  } catch {
    return '0.0.0'
  }
}

/**
 * Mount the media route.
 * @param ctx - context carrying the web server.
 */
export function apply(ctx) {
  ctx.effect(() => {
    const handler = async (req, res) => {
      const json = (status, body, extra = {}) => {
        const text = JSON.stringify(body)
        res.writeHead(status, {
          'content-type': 'application/json; charset=utf-8',
          'cache-control': 'no-store',
          ...extra,
        })
        res.end(text)
      }

      try {
        const url = new URL(req.url ?? '/', 'http://dsh')
        const rel = decodeURIComponent(url.pathname.slice(ROUTE.length + 1))

        if (rel === 'manifest.json' || rel === '') {
          json(200, await buildManifest())
          return
        }

        const found = await firstFile(candidates(rel))
        if (!found) {
          json(404, { ok: false, error: 'not found', path: rel })
          return
        }

        const ext = path.extname(found.abs).toLowerCase()
        const immutable = !found.abs.startsWith(userRoot())
        res.writeHead(200, {
          'content-type': MIME[ext] ?? 'application/octet-stream',
          'content-length': String(found.size),
          // Package assets never change for a given version; user assets may be
          // replaced by the user at any time, so they are revalidated.
          'cache-control': immutable ? 'public, max-age=604800, immutable' : 'no-cache',
          'accept-ranges': 'none',
        })
        if (req.method === 'HEAD') {
          res.end()
          return
        }
        await new Promise((resolve, reject) => {
          const stream = createReadStream(found.abs)
          stream.on('error', reject)
          stream.on('end', resolve)
          stream.pipe(res)
        })
      } catch (error) {
        if (!res.headersSent) {
          json(500, { ok: false, error: String(error?.message ?? error) })
        } else {
          res.end()
        }
      }
    }

    return ctx.webServer.register({ kind: 'prefix', path: ROUTE, handler })
  }, `${NS}: media route`)

  ctx.logger?.info?.(`[${NS}] media route mounted at ${ROUTE} (user root: ${userRoot()})`)
}
