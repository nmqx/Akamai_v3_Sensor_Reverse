const { JSDOM } = require('jsdom');
const fs = require('fs');

const cookiesJson = process.argv[2];
const scriptPath = process.argv[3];
const fpPath = process.argv[4] || '';

if (!cookiesJson || !scriptPath || !fpPath) {
    console.error('Usage: node jsdom_sensor_gen.js <cookies_json> <script_path> <fingerprint_json_path>');
    process.exit(1);
}

const cookies = JSON.parse(cookiesJson);
const script = fs.readFileSync(scriptPath, 'utf-8');
const fp = JSON.parse(fs.readFileSync(fpPath, 'utf-8'));

const SENSOR_URL = 'https://login.basic-fit.com/9Z8_LJx8U/FfIn1xEbA/t2taphkz4zk6Xk/EA1mYRtQBw/AjZ6O31J/O30B';
const t0 = Date.now();
const capturedPosts = [];
const sigs = fp.audio.signals || [];

let createCanvas;
try { createCanvas = require('canvas').createCanvas; } catch {}

const nav = fp.navigator;
const scr = fp.screen;
const win = fp.window;
const gpu = fp.gpu;
const wgl = fp.webgl;
const audioValues = fp.audio.values || {};
const mem = fp.memory;
const bat = fp.battery;

const dom = new JSDOM('<!DOCTYPE html><html><head></head><body></body></html>', {
    url: 'https://login.basic-fit.com/',
    runScripts: 'dangerously',
    pretendToBeVisual: true,
    beforeParse(w) {
        // Hide Node.js globals
        for (const g of ['process', 'module', 'exports', 'require', 'Buffer', '__filename', '__dirname'])
            Object.defineProperty(w, g, { get: () => undefined, configurable: true });
        Object.defineProperty(w, 'global', { get: () => w, configurable: true });
        Object.defineProperty(w.document, 'readyState', { get: () => 'complete', configurable: true });

        // Navigator
        const navProps = {
            userAgent: nav.userAgent, platform: nav.platform || 'Win32',
            vendor: 'Google Inc.', webdriver: false,
            language: 'fr-FR', languages: ['fr-FR', 'fr'],
            hardwareConcurrency: nav.hardwareConcurrency || 8,
            deviceMemory: nav.deviceMemory || 8,
            maxTouchPoints: nav.maxTouchPoints || 0,
            cookieEnabled: true, onLine: true, pdfViewerEnabled: true,
            doNotTrack: nav.doNotTrack || null,
            appName: nav.appName || 'Netscape', appCodeName: nav.appCodeName || 'Mozilla',
            product: nav.product || 'Gecko', productSub: nav.productSub || '20030107',
            appVersion: nav.appVersion || nav.userAgent.replace('Mozilla/', ''),
        };
        for (const [k, v] of Object.entries(navProps))
            Object.defineProperty(w.navigator, k, { get: () => v, configurable: true });

        Object.defineProperty(w.navigator, 'connection', { get: () => ({ effectiveType: '4g', rtt: 50, downlink: 10, saveData: false }), configurable: true });
        Object.defineProperty(w.navigator, 'getBattery', {
            value: () => Promise.resolve({
                charging: bat.charging !== undefined ? bat.charging : true,
                chargingTime: bat.chargingTime || 0,
                dischargingTime: bat.dischargingTime || Infinity,
                level: bat.level !== undefined ? bat.level : 1,
                addEventListener: () => {},
            }), configurable: true
        });
        Object.defineProperty(w.navigator, 'mediaDevices', { get: () => ({ enumerateDevices: () => Promise.resolve([]) }), configurable: true });
        Object.defineProperty(w.navigator, 'permissions', { get: () => ({ query: () => Promise.resolve({ state: 'prompt', onchange: null }) }), configurable: true });

        const pl = [
            { name: 'PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format', length: 0 },
            { name: 'Chrome PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format', length: 0 },
            { name: 'Chromium PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format', length: 0 },
            { name: 'Microsoft Edge PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format', length: 0 },
            { name: 'WebKit built-in PDF', filename: 'internal-pdf-viewer', description: 'Portable Document Format', length: 0 },
        ];
        Object.defineProperty(w.navigator, 'plugins', {
            get: () => { const o = { length: 5, item: i => pl[i], namedItem: n => pl.find(p => p.name === n), refresh: () => {}, [Symbol.iterator]: function*() { for (const p of pl) yield p; } }; for (let i = 0; i < 5; i++) o[i] = pl[i]; return o; },
            configurable: true
        });
        Object.defineProperty(w.navigator, 'mimeTypes', {
            get: () => { const mt = { type: 'application/pdf', suffixes: 'pdf', description: 'Portable Document Format', enabledPlugin: pl[0] }; return { length: 2, 0: mt, 1: mt, item: () => mt, namedItem: () => mt, [Symbol.iterator]: function*() { yield mt; yield mt; } }; },
            configurable: true
        });

        // Screen
        for (const [k, v] of Object.entries({
            width: scr.width || 1920, height: scr.height || 1080,
            availWidth: scr.availWidth || 1920, availHeight: scr.availHeight || 1032,
            colorDepth: scr.colorDepth || 24, pixelDepth: scr.pixelDepth || 24,
            availLeft: scr.availLeft || 0, availTop: scr.availTop || 0,
        })) Object.defineProperty(w.screen, k, { get: () => v, configurable: true });
        Object.defineProperty(w.screen, 'orientation', { get: () => ({ angle: 0, type: 'landscape-primary', onchange: null }), configurable: true });

        // Window
        for (const [k, v] of Object.entries({
            innerWidth: win.innerWidth || 1600, innerHeight: win.innerHeight || 900,
            outerWidth: win.outerWidth || 1600, outerHeight: win.outerHeight || 900,
            devicePixelRatio: win.devicePixelRatio || 1,
            screenX: win.screenX || 0, screenY: win.screenY || 0,
            screenLeft: win.screenX || 0, screenTop: win.screenY || 0,
            scrollX: 0, scrollY: 0, pageXOffset: 0, pageYOffset: 0,
        })) Object.defineProperty(w, k, { get: () => v, configurable: true });
        w.scrollTo = w.scroll = w.scrollBy = () => {};

        // Performance
        w.performance.now = () => Date.now() - t0;
        w.performance.timing = {
            navigationStart: t0, unloadEventStart: 0, unloadEventEnd: 0,
            redirectStart: 0, redirectEnd: 0, fetchStart: t0 + 1,
            domainLookupStart: t0 + 2, domainLookupEnd: t0 + 10,
            connectStart: t0 + 10, connectEnd: t0 + 50,
            secureConnectionStart: t0 + 20, requestStart: t0 + 50,
            responseStart: t0 + 100, responseEnd: t0 + 200,
            domLoading: t0 + 200, domInteractive: t0 + 500,
            domContentLoadedEventStart: t0 + 500, domContentLoadedEventEnd: t0 + 510,
            domComplete: t0 + 800, loadEventStart: t0 + 800, loadEventEnd: t0 + 810,
        };
        w.performance.memory = { usedJSHeapSize: 35e6, totalJSHeapSize: 50e6, jsHeapSizeLimit: (mem && mem.jsHeapSizeLimit) || 2172649472 };
        w.performance.getEntriesByType = w.performance.getEntriesByName = w.performance.getEntries = () => [];
        w.performance.mark = w.performance.measure = w.performance.clearMarks = w.performance.clearMeasures = () => {};

        // Chrome
        w.chrome = {
            runtime: { connect: () => ({}), sendMessage: () => {} },
            app: { isInstalled: false, InstallState: { DISABLED: 'disabled', INSTALLED: 'installed', NOT_INSTALLED: 'not_installed' }, getIsInstalled: () => false, runningState: () => 'cannot_run' },
            loadTimes: () => ({ requestTime: t0 / 1000, startLoadTime: t0 / 1000, commitLoadTime: (t0 + 100) / 1000, finishDocumentLoadTime: (t0 + 500) / 1000, finishLoadTime: (t0 + 800) / 1000, firstPaintTime: (t0 + 300) / 1000, firstPaintAfterLoadTime: 0, navigationType: 'Other', wasFetchedViaSpdy: false, wasNpnNegotiated: true, npnNegotiatedProtocol: 'h2', wasAlternateProtocolAvailable: false, connectionInfo: 'h2' }),
            csi: () => ({ startE: t0, onloadT: t0 + 500, pageT: 500, tran: 15 })
        };

        w.matchMedia = q => ({ matches: false, media: q, addListener: () => {}, removeListener: () => {}, addEventListener: () => {}, removeEventListener: () => {}, dispatchEvent: () => true, onchange: null });

        const origGetComputed = w.getComputedStyle;
        w.getComputedStyle = (el, pseudo) => {
            try {
                const r = origGetComputed.call(w, el, pseudo);
                return new Proxy(r, { get(t, p) { if (p === 'getPropertyValue') return n => { try { return t.getPropertyValue(n) || ''; } catch { return ''; } }; try { return t[p]; } catch { return ''; } } });
            } catch {
                return new Proxy({}, { get(_, p) { if (p === 'getPropertyValue') return () => ''; if (p === 'length') return 0; return ''; } });
            }
        };

        w.Notification = class Notification { constructor() {} static get permission() { return 'default'; } static requestPermission() { return Promise.resolve('default'); } };
        w.Notification.permission = 'default';
        w.speechSynthesis = { getVoices: () => [], speak: () => {}, cancel: () => {}, pause: () => {}, resume: () => {}, pending: false, speaking: false, paused: false };

        // Canvas / WebGL
        const origCE = w.document.createElement.bind(w.document);
        w.document.createElement = function(tag, opts) {
            const el = origCE(tag, opts);
            if (tag.toLowerCase() === 'canvas') {
                const origGC = el.getContext ? el.getContext.bind(el) : () => null;
                el.getContext = function(type) {
                    if (type === '2d' && createCanvas) {
                        const c = createCanvas(el.width || 300, el.height || 150);
                        const ctx = c.getContext('2d');
                        el.toDataURL = m => c.toDataURL(m);
                        el.toBlob = cb => { cb(null); };
                        return ctx;
                    }
                    if (type === 'webgl' || type === 'webgl2' || type === 'experimental-webgl') {
                        const paramMap = wgl.params || {};
                        return new Proxy({}, { get(_, p) {
                            if (p === 'canvas') return el;
                            if (p === 'drawingBufferWidth') return el.width || 300;
                            if (p === 'drawingBufferHeight') return el.height || 150;
                            if (p === 'getExtension') return name => {
                                if (name === 'WEBGL_debug_renderer_info') return { UNMASKED_VENDOR_WEBGL: 37445, UNMASKED_RENDERER_WEBGL: 37446 };
                                if ((wgl.supportedExtensions || []).includes(name)) return {};
                                return null;
                            };
                            if (p === 'getParameter') return param => {
                                if (param === 37445) return gpu.vendor;
                                if (param === 37446) return gpu.renderer;
                                const key = String(param);
                                if (paramMap[key]) {
                                    const e = paramMap[key];
                                    if (e.type === 'Int32Array') return new Int32Array(e.value);
                                    if (e.type === 'Float32Array') return new Float32Array(e.value);
                                    return e.value;
                                }
                                return 0;
                            };
                            if (p === 'getSupportedExtensions') return () => wgl.supportedExtensions || [];
                            if (p === 'getShaderPrecisionFormat') return (st, pt) => {
                                const m = (wgl.shaderPrecisionFormats || []).find(f => f.shaderType === st && f.precisionType === pt);
                                return m ? m.r : { rangeMin: 127, rangeMax: 127, precision: 23 };
                            };
                            if (p === 'getContextAttributes') return () => wgl.contextAttributes || { alpha: true, antialias: true, depth: true };
                            if (typeof p === 'string' && /^[A-Z_]+$/.test(p)) return 0;
                            if (typeof p === 'string' && /^(create|bind|enable|disable|clear|draw|tex|use|viewport|flush|finish|compile|link|attach|shader|buffer|vertex|delete|active|blend|depth|stencil|scissor|color|pixel|read|uniform|get)/.test(p)) return () => {};
                            return undefined;
                        }, set() { return true; } });
                    }
                    try { return origGC(type); } catch { return null; }
                };
            }
            return el;
        };

        // Audio with real fpgen signals
        w.AudioContext = w.webkitAudioContext = class AudioContext {
            constructor() { this.sampleRate = 44100; this.state = 'running'; this.currentTime = 0; this.baseLatency = 0.005333; }
            close() { return Promise.resolve(); } resume() { return Promise.resolve(); }
            createOscillator() { return { type: 'sine', frequency: { value: 440, setValueAtTime: () => {} }, connect: () => {}, start: () => {}, stop: () => {}, disconnect: () => {} }; }
            createAnalyser() { return { fftSize: 2048, frequencyBinCount: 1024, connect: () => {}, disconnect: () => {}, getFloatFrequencyData: a => a.fill(-100), getByteFrequencyData: a => a.fill(0), channelCount: 2, numberOfInputs: 1, numberOfOutputs: 1 }; }
            createGain() { return { gain: { value: 1 }, connect: () => {}, disconnect: () => {} }; }
            createDynamicsCompressor() { return { threshold: { value: -24 }, knee: { value: 30 }, ratio: { value: 12 }, attack: { value: 0.003 }, release: { value: 0.25 }, reduction: 0, connect: () => {}, disconnect: () => {} }; }
            createBiquadFilter() { return { type: 'lowpass', frequency: { value: 350, setValueAtTime: () => {} }, Q: { value: 1 }, gain: { value: 0 }, connect: () => {}, disconnect: () => {} }; }
            createBuffer(c, l, r) { return { numberOfChannels: c, length: l, sampleRate: r, getChannelData: () => { const a = new Float32Array(l); for (let i = 0; i < Math.min(l, sigs.length); i++) a[i] = sigs[i]; return a; }, duration: l / r }; }
            createBufferSource() { return { buffer: null, connect: () => {}, start: () => {}, stop: () => {}, disconnect: () => {} }; }
            createScriptProcessor() { return { connect: () => {}, disconnect: () => {}, onaudioprocess: null }; }
            get destination() { return { numberOfInputs: 0, numberOfOutputs: 1, channelCount: 2 }; }
        };
        w.OfflineAudioContext = class OfflineAudioContext {
            constructor(c, l, r) { this.sampleRate = r || 44100; this.length = l || 44100; this.state = 'suspended'; this.currentTime = 0; }
            startRendering() {
                const len = this.length, sr = this.sampleRate;
                const buf = { numberOfChannels: 1, length: len, sampleRate: sr, getChannelData: () => { const a = new Float32Array(len); for (let i = 0; i < Math.min(len, sigs.length); i++) a[i] = sigs[i]; return a; }, duration: len / sr };
                return Promise.resolve(buf);
            }
            oncomplete = null;
        };

        // Crypto
        if (!w.crypto) w.crypto = {};
        if (!w.crypto.getRandomValues) w.crypto.getRandomValues = arr => { for (let i = 0; i < arr.length; i++) arr[i] = Math.floor(Math.random() * 256); return arr; };
        if (!w.crypto.subtle) w.crypto.subtle = { digest: () => Promise.resolve(new ArrayBuffer(32)) };
        if (!w.crypto.randomUUID) w.crypto.randomUUID = () => 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => { const r = Math.random() * 16 | 0; return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16); });

        // Storage
        const storage = {};
        w.localStorage = w.sessionStorage = { getItem: k => storage[k] || null, setItem: (k, v) => { storage[k] = String(v); }, removeItem: k => { delete storage[k]; }, clear: () => { for (const k in storage) delete storage[k]; }, get length() { return Object.keys(storage).length; }, key: i => Object.keys(storage)[i] || null };

        // WebRTC
        w.RTCPeerConnection = w.webkitRTCPeerConnection = class RTCPeerConnection { constructor() {} createDataChannel() { return {}; } createOffer() { return Promise.resolve({ type: 'offer', sdp: '' }); } setLocalDescription() { return Promise.resolve(); } close() {} addEventListener() {} removeEventListener() {} };

        // RAF
        let rafId = 0;
        w.requestAnimationFrame = cb => { rafId++; setTimeout(() => { try { cb(Date.now() - t0); } catch {} }, 16); return rafId; };
        w.cancelAnimationFrame = () => {};

        // Visibility
        Object.defineProperty(w.document, 'hidden', { get: () => false, configurable: true });
        Object.defineProperty(w.document, 'visibilityState', { get: () => 'visible', configurable: true });
        w.document.hasFocus = () => true;

        // XHR — captures POST bodies (the natural sensor flow)
        w.XMLHttpRequest = class FakeXHR {
            constructor() { this.readyState = 0; this.status = 0; this.responseText = ''; this.response = ''; this.withCredentials = false; this.upload = { addEventListener: () => {} }; }
            open(m, u) { this._method = m; this._url = u; this.readyState = 1; }
            setRequestHeader() {}
            send(body) {
                if (this._method === 'POST' && body) {
                    capturedPosts.push({ url: this._url, body: typeof body === 'string' ? body : String(body) });
                }
                this.readyState = 4; this.status = 200; this.responseText = '{"success":true}'; this.response = '{"success":true}';
                const s = this;
                setTimeout(() => { try { if (s.onreadystatechange) s.onreadystatechange(); } catch {} try { if (s.onload) s.onload(); } catch {} try { if (s.onloadend) s.onloadend(); } catch {} }, 5);
            }
            abort() {} getResponseHeader() { return null; } getAllResponseHeaders() { return ''; }
            addEventListener(ev, fn) { this['on' + ev] = fn; } removeEventListener() {} overrideMimeType() {} dispatchEvent() {}
        };

        w.fetch = function(url, opts) {
            if (opts && opts.method === 'POST' && opts.body) {
                capturedPosts.push({ url, body: opts.body, via: 'fetch' });
            }
            return Promise.resolve(new w.Response('{"success":true}', { status: 200 }));
        };

        // Misc
        w.history.pushState = w.history.replaceState = () => {};
        w.postMessage = () => {};
    }
});

// Document dimensions
try {
    const iw = win.innerWidth || 1600, ih = win.innerHeight || 900;
    const de = dom.window.document.documentElement;
    if (de) { for (const k of ['clientWidth', 'scrollWidth']) Object.defineProperty(de, k, { get: () => iw, configurable: true }); for (const k of ['clientHeight', 'scrollHeight']) Object.defineProperty(de, k, { get: () => ih, configurable: true }); }
    const b = dom.window.document.body;
    if (b) { for (const k of ['clientWidth', 'scrollWidth']) Object.defineProperty(b, k, { get: () => iw, configurable: true }); for (const k of ['clientHeight', 'scrollHeight']) Object.defineProperty(b, k, { get: () => ih, configurable: true }); }
} catch {}

// Cookies
for (const [k, v] of Object.entries(cookies)) {
    try { dom.window.document.cookie = k + '=' + v + '; path=/'; } catch {}
}

// _appath and currentScript
const sEl = dom.window.document.createElement('script');
sEl.textContent = 'var _appath="/9Z8_LJx8U/FfIn1xEbA/t2taphkz4zk6Xk/EA1mYRtQBw/AjZ6O31J/O30B";';
dom.window.document.head.appendChild(sEl);
Object.defineProperty(dom.window.document, 'currentScript', { get: () => ({ src: SENSOR_URL, getAttribute: n => n === 'src' ? SENSOR_URL : null, async: false, defer: false, type: '', charset: '' }), configurable: true });

// Eval sensor script
try {
    dom.window.eval(script);
} catch (e) {
    process.stderr.write('EVAL_ERROR: ' + e.message.substring(0, 300) + '\n');
    process.exit(1);
}

// Simulate mouse/keyboard events
function simulateEvents() {
    const w = dom.window, doc = w.document;
    const iw = win.innerWidth || 1600, ih = win.innerHeight || 900;
    for (let i = 0; i < 30; i++) {
        const x = 100 + Math.floor(Math.random() * (iw - 200));
        const y = 50 + Math.floor(Math.random() * (ih - 100));
        try { doc.dispatchEvent(new w.MouseEvent('mousemove', { clientX: x, clientY: y, screenX: x, screenY: y + 80, bubbles: true })); } catch {}
    }
    for (let i = 0; i < 3; i++) {
        const x = 200 + Math.floor(Math.random() * (iw - 400));
        const y = 100 + Math.floor(Math.random() * (ih - 200));
        try {
            doc.dispatchEvent(new w.MouseEvent('mousedown', { clientX: x, clientY: y, bubbles: true }));
            doc.dispatchEvent(new w.MouseEvent('mouseup', { clientX: x, clientY: y, bubbles: true }));
            doc.dispatchEvent(new w.MouseEvent('click', { clientX: x, clientY: y, bubbles: true }));
        } catch {}
    }
    for (const key of ['a', 's', 'd', 'f']) {
        try { doc.dispatchEvent(new w.KeyboardEvent('keydown', { key, code: 'Key' + key.toUpperCase(), keyCode: key.charCodeAt(0), bubbles: true })); } catch {}
        try { doc.dispatchEvent(new w.KeyboardEvent('keyup', { key, code: 'Key' + key.toUpperCase(), keyCode: key.charCodeAt(0), bubbles: true })); } catch {}
    }
}

// Run events at intervals, then output first captured POST
simulateEvents();
setTimeout(simulateEvents, 500);
setTimeout(simulateEvents, 1500);
setTimeout(simulateEvents, 2500);

setTimeout(() => {
    if (capturedPosts.length === 0) {
        process.stderr.write('ERROR: no sensor POSTs captured after 4s\n');
        process.exit(1);
    }

    process.stderr.write('captured=' + capturedPosts.length + ' posts\n');

    // Log f1 for first post
    try {
        const parsed = JSON.parse(capturedPosts[0].body);
        if (parsed.sensor_data) {
            const parts = parsed.sensor_data.split(';');
            process.stderr.write('f1=' + parts[1] + ' ver=' + parts[0] + ' counter=' + parts[4] + '\n');
        }
    } catch {}

    // Output ALL captured posts — each body is already {"sensor_data":"..."} format
    const bodies = capturedPosts.map(p => p.body);
    console.log(JSON.stringify({ posts: bodies }));

    dom.window.close();
    process.exit(0);
}, 4000);
