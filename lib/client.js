/**
 * dsh-nyanko-sensei — browser half.
 *
 * A hand-written `__ModuleLoader__` bundle, loaded by the host's client module
 * graph from the package's `./client` export. There is deliberately no build
 * step and no framework: the pet is plain DOM, so it can be read and audited in
 * one file, and it cannot break when the GUI's React tree changes shape.
 *
 * The pet renders into a `position: fixed` container appended to `<body>`,
 * *not* into a UI slot. That is a deliberate choice: a desktop pet is chrome
 * that outlives any particular panel, it must not be clipped by a scroll
 * container, and it should survive the GUI rearranging its slots between
 * versions. Nothing in the DSH tree is patched or mutated.
 *
 * Structure:
 *   manifest → settings → animation machine → interaction → voice → autonomy
 *
 * Every subsystem is wrapped so that a failure degrades the pet rather than the
 * page: if the voice file is missing the pet is silent, if the manifest route
 * is absent the built-in asset list is used, if any watcher throws it is
 * dropped and the pet keeps animating.
 */

window.__ModuleLoader__.load({
	id: "dsh-nyanko-sensei",
	factory: (require) => {
		var module = { exports: {} };
		var exports = module.exports;
		Object.defineProperty(exports, Symbol.toStringTag, { value: "Module" });

		const NS = "dsh-nyanko-sensei";
		const ROUTE = "/" + NS;

		/** Client services this bundle wants. Slots is optional; locale is a nicety. */
		const inject = ["slots"];

		/* ------------------------------------------------------------------ *
		 * Animations
		 * ------------------------------------------------------------------ */

		/**
		 * Every animation the pet ships. The host manifest is authoritative when
		 * it is reachable; this table is the fallback and also carries the
		 * semantics the manifest cannot know.
		 *
		 * `loop: false` marks a one-shot reaction that returns to its parent
		 * state; `fps` is the authored frame rate, used for the CSS fallback.
		 */
		const ANIMS = {
			idle: { loop: true, ms: 900, weight: 30, pool: "ambient" },
			blink: { loop: false, ms: 420, weight: 12, pool: "ambient", next: "idle" },
			walk: { loop: true, ms: 900, weight: 14, pool: "ambient" },
			sit: { loop: true, ms: 1100, weight: 10, pool: "ambient" },
			yawn: { loop: false, ms: 1400, weight: 6, pool: "ambient", next: "idle" },
			sleep: { loop: true, ms: 1400, weight: 8, pool: "ambient" },
			happy: { loop: false, ms: 1200, weight: 0, next: "idle", voice: ["natsume", "happy"] },
			angry: { loop: false, ms: 1200, weight: 0, next: "idle", voice: ["angry"] },
			surprised: { loop: false, ms: 1000, weight: 0, next: "idle", voice: ["surprised"] },
			eat: { loop: false, ms: 1600, weight: 0, next: "idle", voice: ["eat"] },
			drag: { loop: true, ms: 700, weight: 0 },
			beast: { loop: false, ms: 2000, weight: 0, next: "idle", special: true },
		};

		/** Animation order used for the fallback asset list and the settings list. */
		const ANIM_NAMES = Object.keys(ANIMS);

		/* ------------------------------------------------------------------ *
		 * Settings
		 * ------------------------------------------------------------------ */

		const STORE_KEY = NS + ":settings";

		const DEFAULTS = {
			visible: true,
			size: 180,
			corner: "bottom-right",
			marginX: 28,
			marginY: 28,
			speed: 60,
			activity: "balanced", // quiet | balanced | lively
			voiceEnabled: true,
			voiceVolume: 0.9,
			voicePack: "default",
			clickVoice: "natsume",
			bubbles: true,
			bubbleMs: 4200,
			reactToAgent: true,
			wander: true,
			showSettingsHint: true,
		};

		/** How often the pet looks for something to do, per activity level. */
		const ACTIVITY = {
			quiet: { idleMs: [14000, 30000], wanderChance: 0.12, chatter: 0.0 },
			balanced: { idleMs: [7000, 16000], wanderChance: 0.3, chatter: 0.05 },
			lively: { idleMs: [3500, 8000], wanderChance: 0.5, chatter: 0.14 },
		};

		/** Lines the pet mutters to itself, per activity level and mood. */
		const LINES = {
			greet: ["夏目，你又带奇怪的家伙回来了？", "哼，本大爷可是很忙的。", "又是我看家？"],
			happy: ["ニャンコ先生、ご機嫌です。", "不错不错，今天有团子吃。", "なつめ！"],
			angry: ["别拽本大爷的尾巴！", "哼，不知好歹。", "放开我，你这个笨蛋！"],
			sleepy: ["唔……再睡五分钟……", "呼……呼……", "别吵，本大爷在修炼。"],
			work: ["你把本大爷晾着，自己在忙什么？", "这活儿本大爷一秒就能干完。", "看在你叫我一声先生的份上。"],
			done: ["干完了，给我点心。", "看，本大爷出手就是不一样。", "别客气，团子拿来。"],
			fail: ["啧，这也能出错？", "果然还是得本大爷来。", "夏目，你在干什么啊。"],
			waiting: ["快点决定，本大爷等着呢。", "人类真是磨蹭。", "问你呢，答不答？"],
			beast: ["退下！", "本大爷的真身，看清楚了。", "区区妖怪，也敢放肆。"],
		};

		/** Read persisted settings, merged over the defaults. Never throws. */
		function loadSettings() {
			try {
				const raw = window.localStorage.getItem(STORE_KEY);
				if (!raw) return { ...DEFAULTS };
				const parsed = JSON.parse(raw);
				return { ...DEFAULTS, ...(parsed && typeof parsed === "object" ? parsed : {}) };
			} catch {
				return { ...DEFAULTS };
			}
		}

		/** Persist settings. Never throws (private-mode storage can refuse). */
		function saveSettings(settings) {
			try {
				window.localStorage.setItem(STORE_KEY, JSON.stringify(settings));
			} catch {
				/* the pet still works, it just forgets */
			}
		}

		/* ------------------------------------------------------------------ *
		 * Small utilities
		 * ------------------------------------------------------------------ */

		const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
		const rand = (lo, hi) => lo + Math.random() * (hi - lo);
		const pick = (list) => (list && list.length ? list[Math.floor(Math.random() * list.length)] : undefined);

		/** `prefers-reduced-motion`, sampled live so the OS setting is respected. */
		function reducedMotion() {
			try {
				return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
			} catch {
				return false;
			}
		}

		/** Build a `cssText` string from a plain object. */
		function css(style) {
			return Object.entries(style)
				.map(([k, v]) => `${k.replace(/[A-Z]/g, (m) => "-" + m.toLowerCase())}:${v}`)
				.join(";");
		}

		/** Create an element with an inline style object and optional text. */
		function el(tag, style, text) {
			const node = document.createElement(tag);
			if (style) node.style.cssText = css(style);
			if (text != null) node.textContent = text;
			return node;
		}

		/** Exponential approach used by the drag spring and the walk lerp. */
		function approach(current, target, rate, dt) {
			return current + (target - current) * (1 - Math.exp(-rate * dt));
		}

		/* ------------------------------------------------------------------ *
		 * The pet
		 * ------------------------------------------------------------------ */

		class NyankoSensei {
			constructor(ctx) {
				this.ctx = ctx;
				this.settings = loadSettings();
				this.manifest = null;
				this.voices = []; // [{id, clips:[{id,ext,bytes}]}]
				this.destroyed = false;
				this.timers = new Set();
				this.listeners = [];

				this.pos = { x: 0, y: 0 };
				this.vel = { x: 0, y: 0 };
				this.bob = 0;
				this.bobPhase = 0;
				this.dragging = false;
				this.walkTarget = undefined;
				this.facingRight = true;
				this.state = "idle";
				this.stateUntil = 0;
				this.busyUntil = 0;
				this.lastAgentState = null;
				this.pendingAgent = null;
				this.agentStreak = { state: null, since: 0 };
				this.currentBuffer = 0;
				this.buffers = [];
				this.currentAnim = null;
				this.selected = false;

				this.buildDom();
				this.placeAtCorner();
				this.bindGlobal();
				this.start();
			}

			/* -------------------------------------------------------------- *
			 * DOM
			 * -------------------------------------------------------------- */

			buildDom() {
				const s = this.settings;

				// The container spans the viewport but is click-through; only the
				// pet stage itself accepts pointer events.
				this.root = el("div", {
					position: "fixed",
					inset: "0",
					zIndex: 2147483000,
					pointerEvents: "none",
					contain: "layout style",
				});
				this.root.setAttribute("data-dsh-nyanko-sensei", "root");

				this.stage = el("div", {
					position: "absolute",
					left: "0px",
					top: "0px",
					width: `${s.size}px`,
					height: `${s.size}px`,
					pointerEvents: "auto",
					cursor: "grab",
					userSelect: "none",
					touchAction: "none",
					willChange: "transform",
					transformOrigin: "50% 100%",
					filter: "drop-shadow(0 6px 10px rgba(0,0,0,0.28))",
					transition: "filter 160ms ease",
				});

				// Two video elements double-buffer the animation so a switch is a
				// cross-fade instead of a blank frame.
				for (let i = 0; i < 2; i += 1) {
					const video = el("video", {
						position: "absolute",
						inset: "0",
						width: "100%",
						height: "100%",
						objectFit: "contain",
						opacity: "0",
						transition: `opacity ${reducedMotion() ? 0 : 180}ms ease`,
						pointerEvents: "none",
					});
					video.muted = true;
					video.loop = true;
					video.autoplay = false;
					video.playsInline = true;
					video.setAttribute("playsinline", "");
					video.setAttribute("aria-hidden", "true");
					// A one-shot reaction ends on its own; go back to resting when it
					// does, rather than holding the last frame.
					video.addEventListener("ended", () => {
						if (this.destroyed) return;
						if (video.dataset.anim !== this.currentAnim) return;
						this.busyUntil = 0;
						this.enterIdle();
					});
					this.stage.appendChild(video);
					this.buffers.push(video);
				}
				this.buffers[0].style.opacity = "1";

				this.bubble = el("div", {
					position: "absolute",
					left: "50%",
					bottom: "calc(100% - 8px)",
					transform: "translateX(-50%)",
					maxWidth: "240px",
					width: "max-content",
					padding: "7px 11px",
					borderRadius: "12px",
					background: "var(--dsw-alias-bg-elevated, #ffffff)",
					color: "var(--dsw-alias-text-primary, #1b1b1f)",
					border: "1px solid var(--dsw-alias-border-l2, rgba(0,0,0,0.12))",
					boxShadow: "0 6px 18px rgba(0,0,0,0.18)",
					font: "13px/1.45 system-ui, -apple-system, 'Segoe UI', 'Microsoft YaHei', sans-serif",
					textAlign: "center",
					opacity: "0",
					transition: "opacity 200ms ease, transform 200ms ease",
					pointerEvents: "none",
					display: "none",
					whiteSpace: "pre-wrap",
				});
				this.stage.appendChild(this.bubble);

				// A subtle ring marks the selected state (click-to-move target).
				this.ring = el("div", {
					position: "absolute",
					inset: "6px",
					borderRadius: "50%",
					border: "1.5px dashed var(--dsw-alias-brand-primary, #4d6bfe)",
					opacity: "0",
					transition: "opacity 160ms ease",
					pointerEvents: "none",
				});
				this.stage.appendChild(this.ring);

				this.root.appendChild(this.stage);
				document.body.appendChild(this.root);
				this.applySize();
			}

			applySize() {
				const size = clamp(this.settings.size, 80, 420);
				this.stage.style.width = `${size}px`;
				this.stage.style.height = `${size}px`;
			}

			/* -------------------------------------------------------------- *
			 * Lifecycle helpers
			 * -------------------------------------------------------------- */

			/** `setTimeout` that is tracked so teardown cannot leave it running. */
			after(ms, fn) {
				const id = window.setTimeout(() => {
					this.timers.delete(id);
					if (!this.destroyed) fn();
				}, ms);
				this.timers.add(id);
				return id;
			}

			/** A repeating timer whose next tick is only armed after the last ran. */
			loop(fn, ms) {
				const tick = () => {
					if (this.destroyed) return;
					try {
						fn();
					} catch (error) {
						console.warn(`[${NS}] loop step failed:`, error);
					}
					this.after(ms, tick);
				};
				this.after(ms, tick);
			}

			/** `addEventListener` that is tracked so teardown cannot leak. */
			on(target, type, handler, options) {
				target.addEventListener(type, handler, options);
				this.listeners.push(() => target.removeEventListener(type, handler, options));
			}

			destroy() {
				this.destroyed = true;
				if (this.raf) window.cancelAnimationFrame(this.raf);
				if (this.autonomyTimer) window.clearTimeout(this.autonomyTimer);
				if (this.bubbleTimer) window.clearTimeout(this.bubbleTimer);
				for (const id of this.timers) window.clearTimeout(id);
				this.timers.clear();
				for (const off of this.listeners) {
					try {
						off();
					} catch {
						/* best effort */
					}
				}
				this.listeners.length = 0;
				try {
					this.stopAgentWatch?.();
				} catch {
					/* best effort */
				}
				for (const video of this.buffers) {
					try {
						video.pause();
						video.removeAttribute("src");
					} catch {
						/* best effort */
					}
				}
				this.root.remove();
			}

			/* -------------------------------------------------------------- *
			 * Manifest & assets
			 * -------------------------------------------------------------- */

			async fetchManifest() {
				try {
					const res = await fetch(`${ROUTE}/manifest.json`, { cache: "no-store" });
					if (!res.ok) throw new Error(`HTTP ${res.status}`);
					const body = await res.json();
					this.manifest = body;
					this.voices = Array.isArray(body.voice) ? body.voice : [];
					if (Array.isArray(body.anims) && body.anims.length > 0) {
						this.available = new Set(body.anims);
					}
				} catch (error) {
					console.warn(`[${NS}] manifest unavailable, using built-in asset list:`, error);
				}
				if (!this.available) this.available = new Set(ANIM_NAMES);
			}

			/** URL of an animation asset, honouring an optional per-animation extension. */
			animUrl(name) {
				return `${ROUTE}/anims/${encodeURIComponent(name)}.webm`;
			}

			hasAnim(name) {
				return this.available ? this.available.has(name) : true;
			}

			/* -------------------------------------------------------------- *
			 * Animation machine
			 * -------------------------------------------------------------- */

			/**
			 * Cross-fade to an animation.
			 *
			 * @param name - animation id.
			 * @param options.force - replay even if it is already the current one.
			 * @param options.silent - do not touch state timers (used by drag/back).
			 */
			play(name, options = {}) {
				if (this.destroyed) return;
				if (!this.hasAnim(name)) name = "idle";
				if (name === "beast" && !this.hasAnim("beast")) name = "happy";
				const spec = ANIMS[name] ?? ANIMS.idle;

				if (!options.force && this.currentAnim === name && spec.loop) return;

				const next = this.buffers[1 - this.currentBuffer];
				const prev = this.buffers[this.currentBuffer];
				this.currentBuffer = 1 - this.currentBuffer;
				this.currentAnim = name;

				next.src = this.animUrl(name);
				next.loop = spec.loop !== false;
				next.dataset.anim = name;
				next.currentTime = 0;
				const started = next.play();
				if (started && typeof started.catch === "function") {
					started.catch(() => {
						// Autoplay refusal (or a codec miss) leaves the previous frame
						// up rather than an empty box; the pet stays usable.
						console.warn(`[${NS}] could not play ${name}`);
					});
				}
				next.style.opacity = "1";
				prev.style.opacity = "0";
				// Park the outgoing buffer once the cross-fade is over. Two videos
				// decoding at once is pure waste, and the paused-but-still-visible
				// buffer is what makes a stale frame look like a stuck animation.
				window.setTimeout(() => {
					if (this.destroyed) return;
					if (prev === this.buffers[this.currentBuffer]) return;
					try {
						prev.pause();
					} catch {
						/* already paused */
					}
				}, reducedMotion() ? 0 : 260);

				if (!options.silent) {
					this.state = name;
					if (spec.loop === false) {
						const ms = spec.ms ?? 1000;
						this.busyUntil = Date.now() + ms;
						this.after(ms + 40, () => {
							if (this.currentAnim === name) this.enterIdle();
						});
					} else {
						this.busyUntil = 0;
					}
				}

				if (spec.voice && this.settings.voiceEnabled && options.speak !== false) {
					this.speak(pick(spec.voice));
				}
				return undefined;
			}

			/** Choose and play a resting animation. */
			enterIdle(preferred) {
				if (this.destroyed) return;
				const pool = ["idle", "idle", "idle", "sit", "blink", "sleep", "yawn", "walk"];
				const candidates = pool.filter((n) => this.hasAnim(n));
				const name = preferred && this.hasAnim(preferred) ? preferred : pick(candidates) ?? "idle";
				this.play(name, { force: true, speak: false });
				if (name === "sleep" || name === "yawn") this.say("sleepy", { chance: 0.5 });
			}

			/** Run a one-shot reaction, then fall back to idle. */
			react(name) {
				if (this.destroyed) return;
				this.play(name, { force: true });
			}

			/* -------------------------------------------------------------- *
			 * Positioning & movement
			 * -------------------------------------------------------------- */

			viewport() {
				return {
					w: window.innerWidth || document.documentElement.clientWidth || 1024,
					h: window.innerHeight || document.documentElement.clientHeight || 768,
				};
			}

			placeAtCorner() {
				const s = this.settings;
				const { w, h } = this.viewport();
				const size = clamp(s.size, 80, 420);
				const positions = {
					"bottom-right": [w - size - s.marginX, h - size - s.marginY],
					"bottom-left": [s.marginX, h - size - s.marginY],
					"top-right": [w - size - s.marginX, s.marginY],
					"top-left": [s.marginX, s.marginY],
				};
				const [x, y] = positions[s.corner] ?? positions["bottom-right"];
				this.pos.x = clamp(x, 0, Math.max(0, w - size));
				this.pos.y = clamp(y, 0, Math.max(0, h - size));
				this.render();
			}

			/** Push the model position to the DOM, including the walk bob. */
			render() {
				const bob = this.bob ?? 0;
				this.stage.style.transform =
					`translate3d(${this.pos.x}px, ${this.pos.y + bob}px, 0)`;
				const flip = this.facingRight ? 1 : -1;
				for (const video of this.buffers) {
					video.style.transform = flip === 1 ? "none" : "scaleX(-1)";
				}
			}

			bounds() {
				const { w, h } = this.viewport();
				const size = clamp(this.settings.size, 80, 420);
				return { minX: 0, maxX: Math.max(0, w - size), minY: 0, maxY: Math.max(0, h - size), size };
			}

			/** Walk towards a target x, switching direction and animation to match. */
			startWalkTo(x) {
				const b = this.bounds();
				const target = clamp(x, b.minX, b.maxX);
				if (Math.abs(target - this.pos.x) < 12) return false;
				this.walkTarget = target;
				this.facingRight = target > this.pos.x;
				// A walk owns the position until it lands, so any leftover fling
				// velocity has to go — otherwise the inertia keeps the `walk`
				// branch alive after the target is reached and the pet is stuck
				// mid-stride at rest.
				this.vel.x = 0;
				this.vel.y = 0;
				this.play("walk", { force: true, speak: false });
				this.render();
				return true;
			}

			/* -------------------------------------------------------------- *
			 * Speech bubbles
			 * -------------------------------------------------------------- */

			/** Show a bubble with one of the canned lines for `mood`. */
			say(mood, options = {}) {
				if (!this.settings.bubbles) return;
				if (options.chance != null && Math.random() > options.chance) return;
				const line = options.text ?? pick(LINES[mood] ?? []);
				if (line) this.bubbleText(line);
			}

			/** Show an explicit bubble string. */
			bubbleText(text) {
				if (this.destroyed || !this.settings.bubbles || !text) return;
				this.bubble.textContent = text;
				this.bubble.style.display = "block";
				// Force a reflow so the transition runs even on a rapid re-show.
				void this.bubble.offsetWidth;
				this.bubble.style.opacity = "1";
				this.bubble.style.transform = "translateX(-50%) translateY(-2px)";
				if (this.bubbleTimer) window.clearTimeout(this.bubbleTimer);
				this.bubbleTimer = window.setTimeout(() => this.hideBubble(), this.settings.bubbleMs);
			}

			hideBubble() {
				if (this.destroyed) return;
				this.bubble.style.opacity = "0";
				this.bubble.style.transform = "translateX(-50%)";
				this.bubbleTimer = window.setTimeout(() => {
					if (!this.destroyed && this.bubble.style.opacity === "0") {
						this.bubble.style.display = "none";
					}
				}, 220);
			}

			/* -------------------------------------------------------------- *
			 * Voice
			 * -------------------------------------------------------------- */

			/** Audio extension to request for a clip, from the manifest. */
			voiceUrl(clip) {
				const packId = this.settings.voicePack;
				const pack = this.voices.find((p) => p.id === packId) ?? this.voices.find((p) => p.id === "default");
				if (!pack) return null;
				const entry = (pack.clips ?? []).find((c) => c.id === clip);
				if (!entry) return null;
				const dir = pack.id === "default" ? "" : `${encodeURIComponent(pack.id)}/`;
				return `${ROUTE}/voice/${dir}${encodeURIComponent(clip)}${entry.ext}`;
			}

			/** Play a voice clip by id. Silently does nothing when unavailable. */
			speak(clip) {
				if (!this.settings.voiceEnabled || !clip) return;
				const url = this.voiceUrl(clip);
				if (!url) return;
				try {
					const audio = new Audio(url);
					audio.volume = clamp(this.settings.voiceVolume, 0, 1);
					const played = audio.play();
					if (played && typeof played.catch === "function") played.catch(() => {});
				} catch (error) {
					console.warn(`[${NS}] voice clip ${clip} failed:`, error);
				}
			}

			/** What a left click does: the signature reaction plus its voice line. */
			clickReaction(region) {
				const roll = Math.random();
				let name = "happy";
				if (roll > 0.86) name = "beast";
				else if (roll > 0.7) name = "angry";
				else if (roll > 0.55) name = "surprised";
				else if (roll > 0.42) name = "eat";
				this.react(name);
				// `happy` carries its own voice list; anything else speaks its own id
				// when a clip exists, and falls back to the signature line.
				if (!(ANIMS[name] && ANIMS[name].voice)) {
					const has = this.voiceUrl(name);
					this.speak(has ? name : this.settings.clickVoice);
				}
				if (name === "beast") {
					this.say("beast", { chance: 1 });
				} else if (region === "head") {
					this.say("happy", { chance: 0.5 });
				} else if (region === "tail") {
					this.say("angry", { chance: 0.5 });
				}
			}

			/* -------------------------------------------------------------- *
			 * Interaction
			 * -------------------------------------------------------------- */

			bindGlobal() {
				const stage = this.stage;

				// --- pointer: click, drag, fling -----------------------------
				let drag = null;

				const localPoint = (event) => {
					const rect = stage.getBoundingClientRect();
					return { x: event.clientX - rect.left, y: event.clientY - rect.top, w: rect.width, h: rect.height };
				};

				this.on(stage, "pointerdown", (event) => {
					if (event.button !== 0) return;
					event.preventDefault();
					event.stopPropagation();
					stage.setPointerCapture?.(event.pointerId);
					const point = localPoint(event);
					drag = {
						id: event.pointerId,
						offsetX: point.x,
						offsetY: point.y,
						startX: this.pos.x,
						startY: this.pos.y,
						moved: false,
						samples: [],
					};
					this.walkTarget = undefined;
					this.dragging = true;
					stage.style.cursor = "grabbing";
					this.play("drag", { force: true, speak: false });
				});

				this.on(stage, "pointermove", (event) => {
					if (!drag || event.pointerId !== drag.id) return;
					// The pet is placed by its top-left corner, so the grab offset is
					// what keeps it under the cursor instead of jumping.
					const nx = event.clientX - drag.offsetX;
					const ny = event.clientY - drag.offsetY;
					if (!drag.moved && Math.hypot(nx - drag.startX, ny - drag.startY) < 4) return;
					drag.moved = true;
					const b = this.bounds();
					this.pos.x = clamp(nx, -b.size * 0.3, b.maxX + b.size * 0.3);
					this.pos.y = clamp(ny, 0, b.maxY);
					drag.samples.push({ t: performance.now(), x: this.pos.x, y: this.pos.y });
					while (drag.samples.length > 8) drag.samples.shift();
					this.render();
				});

				const endDrag = (event) => {
					if (!drag || (event && event.pointerId !== drag.id)) return;
					const wasDrag = drag.moved;
					const samples = drag.samples;
					drag = null;
					this.dragging = false;
					stage.style.cursor = "grab";
					stage.releasePointerCapture?.(event?.pointerId);

					if (!wasDrag) {
						const point = event ? localPoint(event) : { x: 0, y: 0, w: 1, h: 1 };
						const region = point.y < point.h * 0.42 ? "head" : point.x > point.w * 0.68 ? "tail" : "body";
						this.onPetClicked(region);
						return;
					}
					// Fling: use the last two samples for a velocity in px/s.
					if (!reducedMotion() && samples.length >= 2) {
						const a = samples[samples.length - 2];
						const b = samples[samples.length - 1];
						const dt = Math.max(16, b.t - a.t) / 1000;
						this.vel.x = clamp((b.x - a.x) / dt, -2600, 2600);
						this.vel.y = clamp((b.y - a.y) / dt, -2600, 2600);
						if (Math.hypot(this.vel.x, this.vel.y) > 140) this.enterIdle();
					} else {
						this.enterIdle();
					}
				};

				this.on(stage, "pointerup", endDrag);
				this.on(stage, "pointercancel", endDrag);

				// --- click selects / sends the pet walking ------------------
				this.on(stage, "click", (event) => event.stopPropagation());

				// --- right click: the quick menu ---------------------------
				this.on(stage, "contextmenu", (event) => {
					event.preventDefault();
					event.stopPropagation();
					this.openMenu(event.clientX, event.clientY);
				});

				// --- click elsewhere walks to that spot ---------------------
				this.on(window, "pointerdown", (event) => {
					if (!this.selected) return;
					if (this.root.contains(event.target)) return;
					this.selected = false;
					this.ring.style.opacity = "0";
					this.startWalkTo(event.clientX - this.settings.size / 2);
				}, true);

				// --- keep the pet on screen across resizes ------------------
				this.on(window, "resize", () => {
					const b = this.bounds();
					this.pos.x = clamp(this.pos.x, 0, b.maxX);
					this.pos.y = clamp(this.pos.y, 0, b.maxY);
					this.render();
				});

				// --- follow the OS reduced-motion setting -------------------
				try {
					const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
					const onChange = () => {
						for (const video of this.buffers) video.style.transition = mq.matches ? "none" : "opacity 180ms ease";
					};
					if (mq.addEventListener) this.on(mq, "change", onChange);
				} catch {
					/* not fatal */
				}
			}

			onPetClicked(region) {
				this.selected = true;
				this.ring.style.opacity = "0.55";
				this.clickReaction(region);
			}

			/* -------------------------------------------------------------- *
			 * Quick menu
			 * -------------------------------------------------------------- */

			openMenu(clientX, clientY) {
				this.closeMenu();
				const menu = el("div", {
					position: "fixed",
					left: "0px",
					top: "0px",
					zIndex: 2147483001,
					minWidth: "188px",
					padding: "6px",
					borderRadius: "10px",
					background: "var(--dsw-alias-bg-elevated, #ffffff)",
					color: "var(--dsw-alias-text-primary, #1b1b1f)",
					border: "1px solid var(--dsw-alias-border-l2, rgba(0,0,0,0.12))",
					boxShadow: "0 10px 30px rgba(0,0,0,0.24)",
					font: "13px/1.5 system-ui, -apple-system, 'Segoe UI', 'Microsoft YaHei', sans-serif",
					pointerEvents: "auto",
				});

				const item = (label, onClick, opts = {}) => {
					const button = el("button", {
						display: "block",
						width: "100%",
						textAlign: "left",
						padding: "7px 10px",
						border: "0",
						borderRadius: "7px",
						background: "transparent",
						color: "inherit",
						font: "inherit",
						cursor: "pointer",
					}, label);
					button.type = "button";
					button.addEventListener("pointerenter", () => {
						button.style.background = "var(--dsw-alias-bg-hover, rgba(127,127,127,0.14))";
					});
					button.addEventListener("pointerleave", () => {
						button.style.background = "transparent";
					});
					button.addEventListener("click", (event) => {
						event.stopPropagation();
						this.closeMenu();
						onClick();
					});
					if (opts.disabled) {
						button.disabled = true;
						button.style.opacity = "0.45";
					}
					return button;
				};

				const heading = (text) => {
					const node = el("div", {
						padding: "6px 10px 2px",
						fontSize: "11px",
						opacity: "0.6",
					}, text);
					return node;
				};

				menu.appendChild(item("呼唤「なつめ」", () => {
					this.speak(this.settings.clickVoice);
					this.react("happy");
					this.bubbleText("なつめ！");
				}, { disabled: !this.voiceUrl(this.settings.clickVoice) }));

				menu.appendChild(item("摸摸头", () => this.react("happy")));
				menu.appendChild(item("变身", () => {
					this.react("beast");
					this.say("beast", { chance: 1 });
				}));
				menu.appendChild(item("睡一会儿", () => this.play("sleep", { force: true, speak: false })));
				menu.appendChild(item("散步", () => {
					const b = this.bounds();
					this.startWalkTo(rand(b.minX, b.maxX));
				}));

				menu.appendChild(el("div", {
					height: "1px",
					margin: "5px 8px",
					background: "var(--dsw-alias-border-l2, rgba(127,127,127,0.22))",
				}));

				menu.appendChild(heading("设置"));
				menu.appendChild(item(`大小 ${this.settings.size}px  ( + / − )`, () => this.bumpSize(20)));
				menu.appendChild(item(this.settings.visible ? "隐藏" : "显示", () => this.setVisible(!this.settings.visible)));
				menu.appendChild(item("回到初始位置", () => {
					this.vel.x = 0;
					this.vel.y = 0;
					this.placeAtCorner();
					this.enterIdle();
				}));

				menu.appendChild(el("div", {
					height: "1px",
					margin: "5px 8px",
					background: "var(--dsw-alias-border-l2, rgba(127,127,127,0.22))",
				}));
				menu.appendChild(item("打开完整设置…", () => this.openPanel()));

				this.root.appendChild(menu);
				this.menu = menu;

				// Keep the menu inside the viewport.
				const rect = menu.getBoundingClientRect();
				const left = clamp(clientX, 6, window.innerWidth - rect.width - 6);
				const top = clamp(clientY, 6, window.innerHeight - rect.height - 6);
				menu.style.left = `${left}px`;
				menu.style.top = `${top}px`;

				this.after(0, () => {
					const close = (event) => {
						if (this.menu && !this.menu.contains(event.target)) this.closeMenu();
					};
					this.menuCloser = close;
					window.addEventListener("pointerdown", close, true);
				});
			}

			closeMenu() {
				if (this.menuCloser) {
					window.removeEventListener("pointerdown", this.menuCloser, true);
					this.menuCloser = undefined;
				}
				this.menu?.remove();
				this.menu = undefined;
			}

			/* -------------------------------------------------------------- *
			 * Settings panel
			 * -------------------------------------------------------------- */

			openPanel() {
				this.closePanel();

				const panel = el("div", {
					position: "fixed",
					right: "18px",
					bottom: "18px",
					zIndex: 2147483001,
					width: "300px",
					maxHeight: "70vh",
					overflowY: "auto",
					padding: "14px 16px 16px",
					borderRadius: "14px",
					background: "var(--dsw-alias-bg-elevated, #ffffff)",
					color: "var(--dsw-alias-text-primary, #1b1b1f)",
					border: "1px solid var(--dsw-alias-border-l2, rgba(0,0,0,0.12))",
					boxShadow: "0 14px 40px rgba(0,0,0,0.28)",
					font: "13px/1.6 system-ui, -apple-system, 'Segoe UI', 'Microsoft YaHei', sans-serif",
					pointerEvents: "auto",
				});

				const row = (label, control) => {
					const wrap = el("label", {
						display: "flex",
						alignItems: "center",
						justifyContent: "space-between",
						gap: "10px",
						padding: "5px 0",
					});
					wrap.appendChild(el("span", { opacity: "0.85" }, label));
					wrap.appendChild(control);
					return wrap;
				};

				const toggle = (value, onChange) => {
					const input = document.createElement("input");
					input.type = "checkbox";
					input.checked = !!value;
					input.style.cssText = "width:16px;height:16px;cursor:pointer;accent-color:var(--dsw-alias-brand-primary,#4d6bfe)";
					input.addEventListener("change", () => onChange(input.checked));
					return input;
				};

				const number = (value, min, max, step, onChange) => {
					const input = document.createElement("input");
					input.type = "range";
					input.min = String(min);
					input.max = String(max);
					input.step = String(step);
					input.value = String(value);
					input.style.cssText = "width:130px;cursor:pointer;accent-color:var(--dsw-alias-brand-primary,#4d6bfe)";
					input.addEventListener("input", () => onChange(Number(input.value)));
					return input;
				};

				const select = (value, options, onChange) => {
					const node = document.createElement("select");
					node.style.cssText = "max-width:150px;padding:2px 4px;border-radius:6px;background:transparent;color:inherit;border:1px solid var(--dsw-alias-border-l2,rgba(0,0,0,0.2))";
					for (const [value2, label] of options) {
						const option = document.createElement("option");
						option.value = value2;
						option.textContent = label;
						if (value2 === value) option.selected = true;
						node.appendChild(option);
					}
					node.addEventListener("change", () => onChange(node.value));
					return node;
				};

				const header = el("div", {
					display: "flex",
					alignItems: "center",
					justifyContent: "space-between",
					marginBottom: "6px",
				});
				header.appendChild(el("strong", { fontSize: "14px" }, "娘口三三 · 桌宠设置"));
				const close = el("button", {
					border: "0",
					background: "transparent",
					color: "inherit",
					cursor: "pointer",
					fontSize: "16px",
					lineHeight: "1",
					padding: "2px 6px",
				}, "×");
				close.type = "button";
				close.addEventListener("click", () => this.closePanel());
				header.appendChild(close);
				panel.appendChild(header);

				panel.appendChild(row("显示桌宠", toggle(this.settings.visible, (v) => this.setVisible(v))));
				panel.appendChild(row("大小", number(this.settings.size, 80, 420, 10, (v) => {
					this.patch({ size: v });
				})));
				panel.appendChild(row("活跃度", select(this.settings.activity, [
					["quiet", "安静"],
					["balanced", "均衡"],
					["lively", "活泼"],
				], (v) => this.patch({ activity: v }))));
				panel.appendChild(row("自由漫游", toggle(this.settings.wander, (v) => this.patch({ wander: v }))));
				panel.appendChild(row("气泡台词", toggle(this.settings.bubbles, (v) => this.patch({ bubbles: v }))));
				panel.appendChild(row("跟随 Agent 状态", toggle(this.settings.reactToAgent, (v) => this.patch({ reactToAgent: v }))));

				panel.appendChild(el("div", {
					height: "1px",
					margin: "9px 0",
					background: "var(--dsw-alias-border-l2, rgba(127,127,127,0.22))",
				}));

				panel.appendChild(el("div", { fontSize: "12px", opacity: "0.7", marginBottom: "4px" }, "语音"));
				panel.appendChild(row("启用语音", toggle(this.settings.voiceEnabled, (v) => this.patch({ voiceEnabled: v }))));
				panel.appendChild(row("音量", number(Math.round(this.settings.voiceVolume * 100), 0, 100, 5, (v) => {
					this.patch({ voiceVolume: v / 100 });
				})));
				const packOptions = (this.voices.length ? this.voices.map((p) => [p.id, p.id]) : [["default", "default"]]);
				panel.appendChild(row("语音包", select(this.settings.voicePack, packOptions, (v) => this.patch({ voicePack: v }))));
				panel.appendChild(row("点击台词", select(this.settings.clickVoice, this.clipOptions(), (v) => this.patch({ clickVoice: v }))));

				const note = el("div", {
					marginTop: "8px",
					padding: "8px 10px",
					borderRadius: "8px",
					background: "var(--dsw-alias-bg-sunken, rgba(127,127,127,0.1))",
					fontSize: "11.5px",
					lineHeight: "1.55",
					opacity: "0.85",
				});
				note.textContent = this.voices.length
					? `已发现语音包：${this.voices.map((p) => `${p.id}(${p.clips.length})`).join("、")}。放入自己的音频：${this.manifest?.userRoot ?? "$DSH_HOME/dsh-nyanko-sensei"}\\voice\\`
					: `未发现任何语音文件。把自己的音频（例：natsume.mp3，动漫原声）放到 ${this.manifest?.userRoot ?? "$DSH_HOME/dsh-nyanko-sensei"}\\voice\\ 后刷新页面即可。`;
				panel.appendChild(note);

				const reset = el("button", {
					marginTop: "10px",
					width: "100%",
					padding: "7px 10px",
					borderRadius: "8px",
					border: "1px solid var(--dsw-alias-border-l2, rgba(0,0,0,0.16))",
					background: "transparent",
					color: "inherit",
					font: "inherit",
					cursor: "pointer",
				}, "恢复默认设置");
				reset.type = "button";
				reset.addEventListener("click", () => {
					this.settings = { ...DEFAULTS };
					saveSettings(this.settings);
					this.applySize();
					this.placeAtCorner();
					this.closePanel();
					this.openPanel();
				});
				panel.appendChild(reset);

				this.root.appendChild(panel);
				this.panel = panel;
			}

			/** Clip ids offered by the selected voice pack (plus common names). */
			clipOptions() {
				const pack = this.voices.find((p) => p.id === this.settings.voicePack) ?? this.voices[0];
				const ids = new Set((pack?.clips ?? []).map((c) => c.id));
				for (const guess of ["natsume", "happy", "angry", "surprised", "eat"]) ids.add(guess);
				return [...ids].sort().map((id) => [id, id]);
			}

			closePanel() {
				this.panel?.remove();
				this.panel = undefined;
			}

			/* -------------------------------------------------------------- *
			 * Settings mutation
			 * -------------------------------------------------------------- */

			patch(changes) {
				this.settings = { ...this.settings, ...changes };
				saveSettings(this.settings);
				if ("size" in changes) this.applySize();
				if ("visible" in changes) this.setVisible(this.settings.visible);
				if ("activity" in changes && this.autonomyTimer) {
					window.clearTimeout(this.autonomyTimer);
					this.scheduleAutonomy();
				}
			}

			bumpSize(delta) {
				const size = clamp(this.settings.size + delta, 80, 420);
				this.patch({ size });
				this.bubbleText(`${size}px`);
			}

			setVisible(visible) {
				this.settings = { ...this.settings, visible };
				saveSettings(this.settings);
				this.stage.style.display = visible ? "" : "none";
			}

			/* -------------------------------------------------------------- *
			 * Autonomy: idle chatter, wandering, and the physics tick
			 * -------------------------------------------------------------- */

			scheduleAutonomy() {
				const profile = ACTIVITY[this.settings.activity] ?? ACTIVITY.balanced;
				const [lo, hi] = profile.idleMs;
				this.autonomyTimer = window.setTimeout(() => {
					if (this.destroyed) return;
					try {
						this.autonomyStep(profile);
					} catch (error) {
						console.warn(`[${NS}] autonomy step failed:`, error);
					}
					this.scheduleAutonomy();
				}, rand(lo, hi));
			}

			autonomyStep(profile) {
				if (this.dragging || this.menu || this.panel) return;
				const b = this.bounds();

				if (this.settings.wander && Math.random() < profile.wanderChance) {
					this.startWalkTo(rand(b.minX, b.maxX));
					return;
				}
				if (Math.random() < profile.chatter) {
					this.say(pick(["happy", "sleepy", "work", "greet"]), { chance: 1 });
					this.play(pick(["happy", "angry", "surprised"]), { force: true, speak: false });
					return;
				}
				this.enterIdle();
			}

			/** One rAF tick: walking, flung inertia, edge bounce, action timeouts. */
			start() {
				this.lastTick = performance.now();

				const tick = (now) => {
					if (this.destroyed) return;
					const dt = Math.min(0.05, (now - this.lastTick) / 1000);
					this.lastTick = now;
					try {
						this.step(dt);
					} catch (error) {
						console.warn(`[${NS}] tick failed:`, error);
					}
					this.raf = window.requestAnimationFrame(tick);
				};
				this.raf = window.requestAnimationFrame(tick);
				this.scheduleAutonomy();
				this.after(600, () => this.enterIdle());
			}

			step(dt) {
				const b = this.bounds();
				let dirty = false;
				const moving = this.walkTarget != null || Math.abs(this.vel.x) > 20 || Math.abs(this.vel.y) > 20;

				// Safety net: the walk sprite must never outlive the movement that
				// justified it. Any other route back to rest goes through enterIdle,
				// but a one-shot reaction whose timer fired mid-walk can slip past,
				// and a permanently mid-stride pet at rest is the one bug users
				// always notice.
				if (!moving && this.currentAnim === "walk") {
					this.enterIdle();
				}

				// Walking: an exponential approach towards the target.
				if (this.walkTarget != null) {
					const before = this.pos.x;
					this.pos.x = approach(this.pos.x, this.walkTarget, 6, dt);
					this.facingRight = this.walkTarget >= this.pos.x;
					if (Math.abs(this.pos.x - this.walkTarget) < 2) {
						this.pos.x = this.walkTarget;
						this.walkTarget = undefined;
						this.enterIdle();
					}
					if (before !== this.pos.x) dirty = true;
				}

				// Flung inertia with wall bounce.
				if (Math.abs(this.vel.x) > 1 || Math.abs(this.vel.y) > 1) {
					this.pos.x += this.vel.x * dt;
					this.pos.y += this.vel.y * dt;
					this.vel.x *= Math.pow(0.06, dt);
					this.vel.y *= Math.pow(0.06, dt);
					const bounce = 0.55;
					if (this.pos.x < 0) {
						this.pos.x = 0;
						this.vel.x = Math.abs(this.vel.x) * bounce;
						this.play("surprised", { force: true, speak: false });
					} else if (this.pos.x > b.maxX) {
						this.pos.x = b.maxX;
						this.vel.x = -Math.abs(this.vel.x) * bounce;
						this.play("surprised", { force: true, speak: false });
					}
					if (this.pos.y < 0) {
						this.pos.y = 0;
						this.vel.y = Math.abs(this.vel.y) * bounce;
					} else if (this.pos.y > b.maxY) {
						this.pos.y = b.maxY;
						this.vel.y = -Math.abs(this.vel.y) * bounce;
					}
					if (Math.hypot(this.vel.x, this.vel.y) < 30) {
						this.vel.x = 0;
						this.vel.y = 0;
						this.enterIdle("happy");
					}
					dirty = true;
				}

				// A slow bob while walking, so movement reads as walking rather than
				// sliding. Disabled under reduced-motion.
				let bob = 0;
				if (!reducedMotion() && (this.walkTarget != null || Math.abs(this.vel.x) > 20)) {
					this.bobPhase = this.bobPhase + dt * 9;
					bob = Math.sin(this.bobPhase) * 2.2;
				}

				if (dirty || bob !== this.bob) {
					this.bob = bob;
					this.render();
				}

				// Hand the pet back to idle after a reaction's time is up, in case a
				// one-shot animation had no `ended` event to trigger it.
				if (this.busyUntil && Date.now() > this.busyUntil + 120) {
					this.busyUntil = 0;
					this.enterIdle();
				}
			}

			/* -------------------------------------------------------------- *
			 * Agent-state awareness
			 * -------------------------------------------------------------- */

			/**
			 * Watch the conversation DOM for activity and map it onto a mood.
			 *
			 * A DOM observer rather than an RPC subscription on purpose: it needs
			 * no host API, survives GUI changes, and degrades to "no signal" —
			 * which just means the pet behaves autonomously.
			 */
			watchAgent() {
				if (!this.settings.reactToAgent) return;
				const target = document.querySelector("main") ?? document.body;
				if (!target) return;

				let last = 0;
				const observer = new MutationObserver(() => {
					const now = Date.now();
					if (now - last < 900) return; // debounce bursty streaming updates
					last = now;
					this.observeAgentActivity();
				});
				try {
					observer.observe(target, { childList: true, subtree: true, characterData: true });
					this.agentObserver = observer;
				} catch {
					/* observation is optional */
				}
				this.stopAgentWatch = () => this.agentObserver?.disconnect();
			}

			/** Turn "the page is busy" into a mood, with hysteresis. */
			observeAgentActivity() {
				if (!this.settings.reactToAgent) return;

				const busy = this.detectBusy();
				if (!busy) return;
				const now = Date.now();
				if (this.agentStreak.state !== busy) {
					this.agentStreak = { state: busy, since: now };
					return;
				}
				if (now - this.agentStreak.since < 1200) return;

				if (busy === this.lastAgentState) return;
				this.lastAgentState = busy;

				if (busy === "working") {
					this.say("work", { chance: 0.18 });
					this.play("walk", { force: true, speak: false });
				} else if (busy === "waiting") {
					this.say("waiting", { chance: 0.3 });
					this.play("sit", { force: true, speak: false });
				} else if (busy === "error") {
					this.react("surprised");
					this.say("fail", { chance: 0.7 });
				} else if (busy === "done") {
					this.react("happy");
					this.say("done", { chance: 0.6 });
				}
			}

			/** Cheap heuristic read of the GUI's current state. */
			detectBusy() {
				try {
					const text = (document.body.innerText || "").slice(-4000);
					if (/(停止|Stop generating|Stop)/.test(text)) return "working";
					if (/(允许|拒绝|Approve|Deny|等待批准|需要你的确认)/.test(text)) return "waiting";
					if (/(出错|失败|Error|Failed)/.test(text)) return "error";
					if (/(完成|已完成|Done|Finished)/.test(text)) return "done";
				} catch {
					/* detection is best effort */
				}
				return null;
			}
		}

		/* ------------------------------------------------------------------ *
		 * Bootstrap
		 * ------------------------------------------------------------------ */

		/** Dictionaries registered with the host locale service when available. */
		const zh = { "pet.title": "娘口三三" };
		const en = { "pet.title": "Nyanko-sensei" };

		function apply(ctx) {
			let pet = null;

			const boot = async () => {
				try {
					pet = new NyankoSensei(ctx);
					await pet.fetchManifest();
					pet.setVisible(pet.settings.visible);
					pet.watchAgent();
					pet.enterIdle();
					console.info(`[${NS}] pet awake at ${pet.animUrl("idle")}`);
				} catch (error) {
					console.error(`[${NS}] pet failed to start:`, error);
				}
			};

			try {
				ctx.effect(() => ctx.locale?.register?.(NS, { zh, en }), `${NS}: dictionaries`);
			} catch {
				/* dictionaries are optional */
			}

			// The container must exist before the pet mounts; `document.body` is
			// ready by the time client plugins apply, but guard anyway.
			if (document.body) void boot();
			else document.addEventListener("DOMContentLoaded", () => void boot(), { once: true });

			ctx.effect(() => () => {
				try {
					pet?.destroy();
				} catch (error) {
					console.warn(`[${NS}] teardown failed:`, error);
				}
			}, `${NS}: teardown`);
		}

		exports.name = NS;
		exports.apply = apply;
		exports.inject = inject;
		exports.DEFAULTS = DEFAULTS;
		exports.ANIMS = ANIMS;
		return module.exports;
	},
});
