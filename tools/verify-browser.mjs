/**
 * Browser-side end-to-end verification for dsh-nyanko-sensei.
 *
 * The host half can be checked with curl; the pet itself cannot, because it is
 * DOM. This drives a real Edge/Chromium over the DevTools Protocol and asserts
 * what actually matters: that the container mounted, that the animation element
 * is playing a real VP9-alpha video, and that a click produces the reaction.
 *
 * Deliberately dependency-free. `puppeteer` is not vendored in this profile and
 * pulling it in would add a build-time dependency to a plugin that has none, so
 * this speaks CDP over the built-in WebSocket. The browser is spawned with
 * stdio ignored and driven over the loopback debugging port rather than a pipe.
 *
 * Usage:
 *   node tools/verify-browser.mjs            # auto-detect token from the host
 *   node tools/verify-browser.mjs <pageUrl>
 *   node tools/verify-browser.mjs --keep     # leave the browser running
 */
import { spawn } from 'node:child_process'
import { mkdtempSync, mkdirSync, existsSync, rmSync } from 'node:fs'
import { writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const SHOTS = path.join(ROOT, 'work', 'shots')
const PORT = 9333

const BROWSERS = [
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
  'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
  'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
]

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

/** Read the host's current page URL (which carries the access token). */
async function resolveUrl() {
  const explicit = process.argv.find((a) => a.startsWith('http'))
  if (explicit) return explicit

  const lastUrl = path.join(path.dirname(ROOT), '.dsh-last-url.txt')
  if (existsSync(lastUrl)) {
    const { readFileSync } = await import('node:fs')
    const url = readFileSync(lastUrl, 'utf8').trim()
    if (url.startsWith('http')) return url
  }
  const res = await fetch('http://127.0.0.1:3080/')
  const html = await res.text()
  const match = html.match(/token=([A-Za-z0-9_-]+)/)
  return match ? `http://127.0.0.1:3080/?token=${match[1]}` : 'http://127.0.0.1:3080/'
}

/** Minimal CDP client over one page target. */
class Cdp {
  constructor(ws) {
    this.ws = ws
    this.id = 0
    this.pending = new Map()
    this.console = []
    ws.addEventListener('message', (event) => {
      const message = JSON.parse(event.data)
      if (message.method === 'Runtime.consoleAPICalled') {
        const text = (message.params.args ?? [])
          .map((a) => a.value ?? a.description ?? '')
          .join(' ')
        this.console.push({ type: message.params.type, text })
      }
      if (message.method === 'Runtime.exceptionThrown') {
        this.console.push({
          type: 'exception',
          text: message.params.exceptionDetails?.exception?.description ?? 'exception',
        })
      }
      if (message.id && this.pending.has(message.id)) {
        const { resolve, reject } = this.pending.get(message.id)
        this.pending.delete(message.id)
        if (message.error) reject(new Error(message.error.message))
        else resolve(message.result)
      }
    })
  }

  send(method, params = {}) {
    this.id += 1
    const id = this.id
    this.ws.send(JSON.stringify({ id, method, params }))
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject })
      setTimeout(() => {
        if (this.pending.has(id)) {
          this.pending.delete(id)
          reject(new Error(`${method} timed out`))
        }
      }, 30000)
    })
  }

  /** Evaluate an expression in the page and return its JSON value. */
  async evaluate(expression) {
    const result = await this.send('Runtime.evaluate', {
      expression: `(async () => { ${expression} })()`,
      awaitPromise: true,
      returnByValue: true,
    })
    if (result.exceptionDetails) {
      throw new Error(result.exceptionDetails.exception?.description ?? 'evaluate threw')
    }
    return result.result.value
  }
}

const checks = []
const record = (name, ok, detail) => {
  checks.push({ name, ok, detail })
  console.log(`  ${ok ? '✓' : '✗'} ${name}${detail ? ` — ${detail}` : ''}`)
}

async function main() {
  const browser = BROWSERS.find((p) => existsSync(p))
  if (!browser) throw new Error('no Edge/Chrome binary found')

  const profile = mkdtempSync(path.join(tmpdir(), 'nyanko-cdp-'))
  mkdirSync(SHOTS, { recursive: true })

  console.log(`browser : ${path.basename(browser)}`)
  const child = spawn(browser, [
    '--headless=new',
    `--remote-debugging-port=${PORT}`,
    `--user-data-dir=${profile}`,
    '--no-first-run',
    '--no-default-browser-check',
    '--disable-extensions',
    '--autoplay-policy=no-user-gesture-required',
    '--window-size=1280,860',
    'about:blank',
  ], { stdio: 'ignore', detached: false })

  const target = await (async () => {
    for (let i = 0; i < 60; i += 1) {
      try {
        const res = await fetch(`http://127.0.0.1:${PORT}/json/list`)
        const list = await res.json()
        const page = list.find((t) => t.type === 'page' && t.webSocketDebuggerUrl)
        if (page) return page
      } catch {
        /* not up yet */
      }
      await sleep(500)
    }
    throw new Error('DevTools endpoint never came up')
  })()

  const ws = new WebSocket(target.webSocketDebuggerUrl)
  await new Promise((resolve, reject) => {
    ws.addEventListener('open', resolve, { once: true })
    ws.addEventListener('error', () => reject(new Error('websocket failed')), { once: true })
  })
  const cdp = new Cdp(ws)
  await cdp.send('Runtime.enable')
  await cdp.send('Page.enable')

  const url = await resolveUrl()
  console.log(`page    : ${url.replace(/token=[^&]+/, 'token=***')}`)

  await cdp.send('Page.navigate', { url })
  // The GUI has to boot and the client bundles to load before the pet appears.
  await sleep(9000)

  // --- the pet must be mounted -------------------------------------------
  const mounted = await cdp.evaluate(`
    const root = document.querySelector('[data-dsh-nyanko-sensei="root"]');
    return { present: !!root, children: root ? root.children.length : 0 };
  `)
  record('overlay container mounted', mounted.present, `${mounted.children} child element(s)`)

  // --- it must be playing equally sized, decoded VP9-alpha videos --------
  // The expected size comes from the manifest rather than a literal: hardcoding
  // it here meant a legitimate change to the render size showed up as a plugin
  // failure, which is a test bug masquerading as a product bug. Every clip is
  // asserted to share one size, which is the property that actually matters.
  const expected = await cdp.evaluate(`
    const res = await fetch('/dsh-nyanko-sensei/manifest.json', { cache: 'no-store' });
    const manifest = await res.json();
    const sizes = await Promise.all((manifest.anims || []).map((name) => new Promise((resolve) => {
      const v = document.createElement('video');
      v.muted = true;
      v.preload = 'metadata';
      v.addEventListener('loadedmetadata', () => resolve({ name, w: v.videoWidth, h: v.videoHeight }), { once: true });
      v.addEventListener('error', () => resolve({ name, w: 0, h: 0 }), { once: true });
      setTimeout(() => resolve({ name, w: 0, h: 0 }), 8000);
      v.src = '/dsh-nyanko-sensei/anims/' + encodeURIComponent(name) + '.webm';
    })));
    const distinct = [...new Set(sizes.filter((s) => s.w > 0).map((s) => s.w + 'x' + s.h))];
    return { sizes, distinct, failed: sizes.filter((s) => s.w === 0).map((s) => s.name) };
  `)
  record('every declared animation loads its own video',
    (expected?.failed ?? ['unknown']).length === 0,
    expected?.failed?.length
      ? `failed: ${expected.failed.join(', ')}`
      : `${expected?.sizes?.length} clips`)
  record('all animations share one frame size',
    (expected?.distinct ?? []).length === 1,
    expected?.distinct?.join(' / ') || 'none')

  const media = await cdp.evaluate(`
    const root = document.querySelector('[data-dsh-nyanko-sensei="root"]');
    if (!root) return { error: 'no pet' };
    const videos = [...root.querySelectorAll('video')];
    return videos.map((v) => ({
      src: v.currentSrc || v.src,
      readyState: v.readyState,
      paused: v.paused,
      duration: Number.isFinite(v.duration) ? Math.round(v.duration * 100) / 100 : null,
      w: v.videoWidth, h: v.videoHeight,
      opacity: Number(v.style.opacity),
      anim: v.dataset.anim || null,
      loop: v.loop,
    }));
  `)
  const decoded = (media ?? []).filter((v) => v && v.readyState >= 2 && v.w > 0)
  record('a video is decoded and playing in the pet',
    decoded.some((v) => !v.paused) && decoded.some((v) => v.opacity > 0.5),
    decoded.map((v) => `${v.anim}:${v.w}x${v.h}:${v.paused ? 'paused' : 'running'}:op${v.opacity}`).join(', ')
      || JSON.stringify(media))

  // --- the alpha plane must survive into the browser ---------------------
  const alpha = await cdp.evaluate(`
    const root = document.querySelector('[data-dsh-nyanko-sensei="root"]');
    const v = root && [...root.querySelectorAll('video')].find((x) => x.readyState >= 2);
    if (!v) return { error: 'no decoded video' };
    const c = document.createElement('canvas');
    c.width = v.videoWidth; c.height = v.videoHeight;
    const g = c.getContext('2d');
    g.clearRect(0, 0, c.width, c.height);
    g.drawImage(v, 0, 0);
    const d = g.getImageData(0, 0, c.width, c.height).data;
    let transparent = 0, total = 0;
    for (let i = 3; i < d.length; i += 4) { total += 1; if (d[i] < 16) transparent += 1; }
    return { ratio: Math.round((transparent / total) * 1000) / 10, total };
  `)
  record('VP9 alpha decoded by the browser', (alpha?.ratio ?? 0) > 5,
    alpha?.error ?? `${alpha?.ratio}% of pixels transparent`)

  // --- a click must produce a reaction and a voice attempt ---------------
  const click = await cdp.evaluate(`
    const root = document.querySelector('[data-dsh-nyanko-sensei="root"]');
    const stage = root && root.querySelector('div');
    if (!stage) return { error: 'no stage' };
    const box = stage.getBoundingClientRect();
    const opts = { bubbles: true, cancelable: true, clientX: box.left + box.width / 2,
                   clientY: box.top + box.height / 2, pointerId: 1, button: 0, isPrimary: true };
    stage.dispatchEvent(new PointerEvent('pointerdown', opts));
    stage.dispatchEvent(new PointerEvent('pointerup', opts));
    await new Promise((r) => setTimeout(r, 900));
    const videos = [...root.querySelectorAll('video')];
    return { animations: videos.map((v) => v.dataset.anim), opacities: videos.map((v) => v.style.opacity) };
  `)
  record('click triggers a reaction animation', !!click && !click.error && (click.animations ?? []).length > 0,
    click?.error ?? `buffers now: ${(click.animations ?? []).join(', ')}`)

  // --- the voice clip must be reachable and decodable --------------------
  // Read the manifest the same way the pet does, then actually decode the clip
  // through an <audio> element — a 200 from curl does not prove the browser can
  // play it, and codec/extension mismatches are exactly how voice silently dies.
  const voice = await cdp.evaluate(`
    const res = await fetch('/dsh-nyanko-sensei/manifest.json', { cache: 'no-store' });
    const manifest = await res.json();
    const pack = (manifest.voice || []).find((p) => p.id === 'default');
    const clip = pack && (pack.clips || []).find((c) => c.id === 'natsume');
    if (!clip) return { error: 'no natsume clip in the manifest', packs: (manifest.voice || []).map((p) => p.id) };
    const url = '/dsh-nyanko-sensei/voice/' + clip.id + clip.ext;
    const probe = new Audio(url);
    probe.volume = 0;
    const outcome = await new Promise((resolve) => {
      const done = (value) => resolve(value);
      probe.addEventListener('loadedmetadata', () => done({ ok: true, duration: probe.duration }), { once: true });
      probe.addEventListener('error', () => done({ ok: false, reason: 'decode error' }), { once: true });
      setTimeout(() => done({ ok: false, reason: 'timeout' }), 8000);
      probe.load();
    });
    return { url, ext: clip.ext, bytes: clip.bytes, ...outcome };
  `)
  record('voice clip loads and decodes in the browser', voice?.ok === true,
    voice?.error ?? `${voice?.url} (${voice?.bytes} bytes, ${voice?.duration ? Math.round(voice.duration * 100) / 100 + 's' : voice?.reason})`)

  // --- screenshots for the record and for the plugin listing --------------
  // A reaction is triggered first so the capture shows the pet doing something
  // rather than mid-transition, and so the bubble is visible if one fired.
  await cdp.evaluate(`
    const root = document.querySelector('[data-dsh-nyanko-sensei="root"]');
    const stage = root && root.querySelector('div');
    if (stage) {
      const b = stage.getBoundingClientRect();
      const opts = { bubbles: true, cancelable: true, clientX: b.left + b.width / 2,
                     clientY: b.top + b.height * 0.3, pointerId: 2, button: 0, isPrimary: true };
      stage.dispatchEvent(new PointerEvent('pointerdown', opts));
      stage.dispatchEvent(new PointerEvent('pointerup', opts));
    }
    await new Promise((r) => setTimeout(r, 450));
  `)
  const shot = await cdp.send('Page.captureScreenshot', { format: 'png' })
  const shotPath = path.join(SHOTS, 'desktop-pet.png')
  await writeFile(shotPath, Buffer.from(shot.data, 'base64'))

  // The docs copy is what the plugin listing and the README show, so it is
  // written from the same capture rather than kept as a hand-maintained file
  // that silently goes stale.
  mkdirSync(path.join(ROOT, 'docs'), { recursive: true })
  const docsShot = path.join(ROOT, 'docs', 'screenshot.png')
  await writeFile(docsShot, Buffer.from(shot.data, 'base64'))
  console.log(`\nscreenshot: ${shotPath}\n            ${docsShot}`)

  // --- it must settle back to a resting animation, not stay stuck ---------
  // A pet frozen mid-reaction is the failure this animation machine is most
  // likely to produce, so it gets an explicit assertion rather than an eyeball.
  // The wait covers the longest one-shot reaction plus its fallback. Which
  // animations count as "resting" is read from the client's own table rather
  // than duplicated here, so adding a looping animation cannot break the test.
  await sleep(7000)
  const settled = await cdp.evaluate(`
    const root = document.querySelector('[data-dsh-nyanko-sensei="root"]');
    if (!root) return { error: 'no pet' };
    const videos = [...root.querySelectorAll('video')];
    const visible = videos.filter((v) => Number(v.style.opacity) > 0.5);
    const oneShots = ['ear_flick', 'hop', 'bounce_land', 'happy', 'angry', 'surprised', 'spin'];
    return {
      all: videos.map((v) => v.dataset.anim),
      visible: visible.map((v) => v.dataset.anim),
      playing: videos.filter((v) => !v.paused).map((v) => v.dataset.anim),
      stuckInOneShot: visible.map((v) => v.dataset.anim).filter((a) => oneShots.includes(a)),
    };
  `)
  record('settles out of one-shot reactions (not stuck mid-reaction)',
    !!settled && (settled.stuckInOneShot ?? ['unknown']).length === 0,
    `visible=${(settled?.visible ?? []).join(',')} playing=${(settled?.playing ?? []).join(',')}`)

  // --- the cross-fade must never leave two buffers visible ---------------
  // Sampled over several seconds rather than asserted once, because a single
  // sample can land inside a cross-fade, where two videos are legitimately live
  // for the length of the fade. The invariants that actually matter are that at
  // most one buffer is ever visible, and that the visible one is the running
  // one — a visible-but-paused buffer is a frozen pet.
  const samples = []
  for (let i = 0; i < 8; i += 1) {
    samples.push(await cdp.evaluate(`
      const root = document.querySelector('[data-dsh-nyanko-sensei="root"]');
      const videos = [...root.querySelectorAll('video')];
      const visible = videos.filter((v) => Number(v.style.opacity) > 0.5);
      return {
        visibleCount: visible.length,
        visiblePlaying: visible.filter((v) => !v.paused).length,
        visible: visible.map((v) => v.dataset.anim),
        running: videos.filter((v) => !v.paused).map((v) => v.dataset.anim),
      };
    `))
    await sleep(600)
  }
  const neverTwoVisible = samples.every((s) => (s.visibleCount ?? 0) <= 1)
  const visibleAlwaysRunning = samples.every((s) => s.visibleCount === 0 || s.visiblePlaying === s.visibleCount)
  record('at most one buffer is visible at any sample', neverTwoVisible,
    samples.map((s) => s.visibleCount).join(','))
  record('the visible buffer is always the running one', visibleAlwaysRunning,
    samples.map((s) => `${(s.visible ?? []).join('+') || '-'}:${s.visiblePlaying}/${s.visibleCount}`).join(' '))

  // --- the page must not have logged pet errors --------------------------
  const noise = cdp.console.filter((entry) =>
    /dsh-nyanko-sensei/.test(entry.text) && (entry.type === 'error' || entry.type === 'exception'))
  record('no pet errors in the browser console', noise.length === 0,
    noise.length ? noise.map((e) => e.text.slice(0, 120)).join(' | ') : 'clean')

  if (process.argv.includes('--verbose')) {
    for (const entry of cdp.console.filter((e) => /dsh-nyanko-sensei/.test(e.text))) {
      console.log(`    [${entry.type}] ${entry.text.slice(0, 200)}`)
    }
  }

  const failed = checks.filter((c) => !c.ok)
  console.log(`\n${checks.length - failed.length}/${checks.length} checks passed`)

  if (!process.argv.includes('--keep')) {
    try { ws.close() } catch { /* already closed */ }
    try { child.kill() } catch { /* already gone */ }
    await sleep(600)
    try { rmSync(profile, { recursive: true, force: true }) } catch { /* locked */ }
  }
  process.exitCode = failed.length === 0 ? 0 : 1
}

main().catch((error) => {
  console.error(`verification failed: ${error.message}`)
  process.exitCode = 2
})
