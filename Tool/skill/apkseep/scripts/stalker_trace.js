/*
 * stalker_trace.js -- record a basic-block-level Stalker trace of one native module.
 *
 * WHY THIS SHAPE
 * --------------
 * Static disassembly of an obfuscated library (OLLVM control-flow flattening and
 * friends) answers "what COULD run". The question that actually breaks the
 * obfuscation is "what DID run, and how often" -- the dispatcher block of a
 * flattened function executes orders of magnitude more often than the real
 * blocks, and that ratio is invisible statically. Frida Stalker answers it:
 * it re-compiles every basic block the target thread executes and reports each
 * block back, without needing symbols, source, or even a loadable disassembler
 * on the host.
 *
 * Three rules keep the trace usable, and violating each one is a documented
 * failure mode:
 *
 *   1. FOLLOW ONE TRIGGER, NOT THE WHOLE PROCESS. Stalker on an unrestricted
 *      thread produces gigabytes and the app dies of slowdown. The trace starts
 *      when a trigger fires (an export call, an offset call, a Java method, or
 *      the main thread) and stops after followMs or when the trigger returns.
 *   2. FILTER TO ONE MODULE. Only blocks whose address falls inside
 *      CONFIG.targetModule are reported (call edges report when either end is
 *      inside). Everything else is dropped on the device, not in post.
 *   3. CAP THE VOLUME. maxBlocks stops the trace instead of letting the log
 *      eat the disk; the DONE line says whether truncation happened.
 *
 * ADAPT TO YOUR TARGET (CONFIG below, or rpc/recv at runtime)
 * -----------------------------------------------------------
 *   targetModule : the .so you are analyzing ('libapp.so', 'libflutter.so', ...)
 *   trigger.kind : 'export'  -- trigger.module + trigger.export (e.g. a JNI fn)
 *                | 'offset'  -- trigger.module + trigger.offset (mod-relative)
 *                | 'java'    -- trigger.cls + trigger.method (Java bridge; the
 *                               classic java->native boundary)
 *                | 'main'    -- follow the main thread right after load; use on
 *                               a quiet/attached process and poke the UI
 *   followMs     : hard stop, so a forgotten trace cannot kill the process
 *   events       : compile = first time a block is translated (dedup'd block
 *                  set + first-visit order = CFG skeleton);
 *                  block = every executed block (execution counts; the
 *                  histogram that exposes the dispatcher);
 *                  call = call edges (call graph into/out of the module);
 *                  exec = per-instruction (ENORMOUS; only for a few hundred
 *                  instructions around a known point; off by default);
 *                  ret = return edges (off by default).
 *   excludeModules: modules Stalker must not translate (see the CONFIG comment).
 *                  Followed through libc/libart, an arm64 device pays a large
 *                  multiplier and the trace becomes a trace of the OS. Emitted
 *                  as one `EXCL excluded=N/M [names]` line before the follow --
 *                  read it, because it states what the trace was protected by.
 *                  A module not yet loaded cannot be excluded; exclusion is
 *                  best-effort and applies to modules already mapped.
 *   zeroEventWarnMs: emits `WARN zero events ...` when a follow delivered
 *                  nothing by then, so a dead pipeline is not mistaken for
 *                  "the code did not run".
 *
 * HOW TO RUN
 * ----------
 *   With the bundled injector (constants must be baked into CONFIG):
 *       python run_probe.py stalker_trace.js 2 --pkg com.example.app --log t.log
 *   With any driver that speaks rpc (no file edit needed):
 *       script.exports.config({ targetModule: 'libapp.so',
 *                               trigger: { kind: 'offset', module: 'libapp.so',
 *                                          offset: 0x1234 } })
 *       script.exports.start()
 *   Or post a config message instead of rpc:
 *       script.post({ type: 'cfg', payload: {...same shape as CONFIG...} })
 *
 * OUTPUT FORMAT (one logical line per event; multi-line batches share one send)
 * ----------------------------------------------------------------------------
 *   READY ...            config echo + module status; nothing works before it
 *   MOD name base=0x.. size=.. path=..
 *                        module base, so offline tools map offsets back
 *   BB <seq> <mod>+0x<offset>
 *                        block first translated (dedup'd CFG skeleton)
 *   BLK <seq> <mod>+0x<offset> [size=<n>]
 *                        block executed (weighted histogram input)
 *   CALL <depth> <from> -> <to>
 *                        call edge; addresses are <module>+0x<off> when the
 *                        module is known, raw hex otherwise
 *   DONE reason=timeout|trigger-leave|maxBlocks|stop-rpc blocks=<n>
 *        blk=<n> calls=<n> truncated=<0|1>
 *   FATAL / TRIG-FAIL    what did not install and why (the script keeps running)
 *
 *   Feed the log to scripts/stalker_report.py for the histogram, the dedup'd
 *   block order, and the call-edge table. See references/
 *   native-dbi-and-deobfuscation.md for the workflow around this trace.
 *
 * TESTED
 * ------
 *   frida 16.7.19 host + frida-server 16.7.19 on Android 11 arm64. See
 *   docs/tool-verification/EXTENSION-native-dbi.md for the observed runs.
 */

'use strict';

/* ===================================================================
 * 1. ADAPT THESE LINES (runtime override also possible -- see the tail)
 * =================================================================== */
var CONFIG = {
    // The only module whose blocks are reported.
    targetModule: 'libc.so',

    // What starts/stops the trace. Examples:
    //   { kind: 'main' }
    //   { kind: 'export', module: 'libnative-lib.so', export: 'Java_com_example_App_check' }
    //   { kind: 'offset', module: 'libapp.so', offset: 0x9f6c0 }
    //   { kind: 'java', cls: 'com.example.app.NativeBridge', method: 'sign' }
    trigger: { kind: 'main' },

    followMs: 4000,        // unfollow after this long, no matter what
    maxBlocks: 100000,     // stop recording past this many reported events
    autoStart: true,       // false = arm triggers but wait for rpc start()

    // Modules Stalker must NOT translate, resolved by name at follow time.
    // Cost is the reason this exists. A followed thread whose execution runs
    // through libc/libart pays a large multiplier on arm64 (community reports
    // 20-50x) and drags the whole device down with it, and a hot library
    // reached through a follow/unfollow cycle is where target processes have
    // died. Excluding the system libraries you are not studying is the
    // difference between a trace of your target and a trace of the OS.
    // The target module is never excluded, even if its name is listed here.
    excludeModules: [
        'libc.so', 'libm.so', 'libdl.so', 'libc++.so', 'libc++_shared.so',
        'libart.so', 'libartbase.so', 'libnativehelper.so',
        'libutils.so', 'libbinder.so', 'libcutils.so', 'libbase.so',
        'libui.so', 'libgui.so', 'libinput.so', 'libhwui.so', 'libskia.so',
        'libEGL.so', 'libGLESv2.so', 'libvulkan.so', 'libandroid.so',
        'liblog.so', 'libziparchive.so', 'libz.so'
    ],
    excludeModulesExtra: [],  // your own: 'libfoo.so', or 'libfoo.so+0x1000' for a sub-range
    zeroEventWarnMs: 1500,    // warn when a follow has produced nothing by then

    events: {
        compile: true,     // first translation of each block (skeleton)
        block: true,       // every executed block (weights)
        call: true,        // call edges
        exec: false,       // per-instruction: huge, opt-in only
        ret: false
    }
};

/* ===================================================================
 * 2. plumbing (no target knowledge below this line)
 * =================================================================== */
var state = {
    started: false,        // trigger installed / main follow armed
    following: false,
    followTid: null,
    target: null,          // Module object of CONFIG.targetModule
    modByName: {},         // addr-cache for cross-module name lookup
    seq: 0, nBB: 0, nBLK: 0, nCALL: 0,
    truncated: false,
    timer: null,
    pending: [],           // batched lines waiting for one send()
    pendingSince: 0
};

function ts() { return new Date().toISOString(); }

function emit(tag, msg) { send({ t: ts(), tag: tag, msg: msg }); }

function flush(force) {
    if (!state.pending.length) return;
    var now = Date.now();
    if (!force && now - state.pendingSince < 120 && state.pending.length < 256) return;
    send({ t: ts(), tag: 'TRACE', msg: state.pending.join('\n') });
    state.pending = [];
    state.pendingSince = now;
}

function line(text) {
    state.pending.push(text);
    flush(false);
}

/* Stalker.parse() with stringify:false yields raw addresses that may arrive
 * as NativePointer, number, or UInt64 depending on the frida version. ptr()
 * normalizes all of them; a null address stays null. */
function asPtr(v) {
    if (v === null || v === undefined) return null;
    if (v && typeof v.equals === 'function') return v;      // already a pointer
    try { return ptr(v); } catch (e) { return null; }
}

function moduleOf(addr) {
    // target module first: the hot path never hits Process.findModuleByAddress
    if (state.target && addr.compare(state.target.base) >= 0 &&
        addr.compare(state.target.base.add(state.target.size)) < 0)
        return state.target;
    // one shared cache for everything else (call edges leaving the module)
    var hit = Process.findModuleByAddress(addr);
    if (hit && !state.modByName[hit.name]) {
        state.modByName[hit.name] = hit;
        line('MOD ' + hit.name + ' base=' + hit.base + ' size=' + hit.size +
             ' path=' + hit.path);
    }
    return hit || null;
}

/* <module>+0x<offset> when the module is known, raw hex otherwise. */
function fmtAddr(addr) {
    var m = moduleOf(addr);
    if (m) return m.name + '+0x' + addr.sub(m.base).toString(16);
    return addr.toString();
}

/* ===================================================================
 * 3. the follow engine
 * =================================================================== */
function onStalkEvents(events) {
    var entries;
    try {
        entries = Stalker.parse(events, { stringify: false, annotate: false });
    } catch (e) {
        emit('FATAL', 'Stalker.parse failed: ' + e);
        endFollow('parse-error');
        return;
    }
    for (var i = 0; i < entries.length; i++) {
        var ev = entries[i];
        var kind = ev[0];
        if (kind === 'compile') {
            var a = asPtr(ev[1]);
            if (!a || !moduleOf(a)) continue;
            state.seq++; state.nBB++;
            line('BB ' + state.seq + ' ' + fmtAddr(a));
        } else if (kind === 'block') {
            var b = asPtr(ev[1]);
            if (!b || !moduleOf(b)) continue;
            state.seq++; state.nBLK++;
            var sz = (ev.length > 2 && typeof ev[2] === 'number') ? ev[2] : null;
            line('BLK ' + state.seq + ' ' + fmtAddr(b) +
                 (sz !== null ? ' size=' + sz : ''));
        } else if (kind === 'call') {
            var from = asPtr(ev[1]), to = asPtr(ev[2]);
            var depth = (ev.length > 3 && typeof ev[3] === 'number') ? ev[3] : '?';
            if (!from || !to) continue;
            var fromIn = !!moduleOf(from), toIn = !!moduleOf(to);
            if (!fromIn && !toIn) continue;              // drop unrelated edges
            state.seq++; state.nCALL++;
            line('CALL ' + depth + ' ' + fmtAddr(from) + ' -> ' + fmtAddr(to));
        }
        // 'exec'/'ret' are opt-in; if enabled they are reported as X/RET lines
        else if (kind === 'exec' && CONFIG.events.exec) {
            var x = asPtr(ev[1]);
            if (!x || !moduleOf(x)) continue;
            state.seq++;
            line('X ' + state.seq + ' ' + fmtAddr(x));
        }
        if (state.seq >= CONFIG.maxBlocks) { endFollow('maxBlocks'); return; }
    }
    flush(true);
}

/* Exclude every configured module that is already mapped. Best-effort by
 * design: a module that is not loaded yet cannot be excluded, so the count
 * emitted here is what the trace is actually protected by -- read it before
 * interpreting a bad trace. Exclusion must happen before follow(). */
function applyExclusions() {
    var names = (CONFIG.excludeModules || []).concat(CONFIG.excludeModulesExtra || []);
    var excluded = [], attempted = 0, missing = [];
    for (var i = 0; i < names.length; i++) {
        var spec = names[i];
        if (!spec) continue;
        var plus = spec.indexOf('+');
        var name = plus > 0 ? spec.substring(0, plus) : spec;
        if (state.target && name === state.target.name) continue;  // never the target
        var mod = null;
        try { mod = Process.findModuleByName(name); } catch (e) { mod = null; }
        if (!mod) { missing.push(name); continue; }
        attempted++;
        try {
            if (plus > 0) {
                var off = parseInt(spec.substring(plus + 1), 16) || 0;
                Stalker.exclude({ base: mod.base.add(off), size: mod.size - off });
            } else {
                Stalker.exclude(mod);
            }
            excluded.push(name);
        } catch (e) {
            emit('EXCL-FAIL', spec + ': ' + e);
        }
    }
    emit('EXCL', 'excluded=' + excluded.length + '/' + attempted +
         ' [' + excluded.join(',') + ']' +
         (missing.length ? ' not-loaded=' + missing.length : ''));
}

function beginFollow(tid, why) {
    if (state.following) return;
    if (!state.target) {
        emit('FATAL', 'target module not loaded, refusing to follow (see READY)');
        return;
    }
    state.following = true;
    state.followTid = tid;
    emit('TRIG', 'following tid=' + tid + ' (' + why + ') module=' +
         state.target.name + ' base=' + state.target.base);
    line('MOD ' + state.target.name + ' base=' + state.target.base +
         ' size=' + state.target.size + ' path=' + state.target.path);

    applyExclusions();

    Stalker.follow(tid, {
        events: {
            call: CONFIG.events.call,
            ret: CONFIG.events.ret,
            exec: CONFIG.events.exec,
            block: CONFIG.events.block,
            compile: CONFIG.events.compile
        },
        onReceive: onStalkEvents
    });

    /* A zero-event trace has two very different meanings -- "nothing executed"
     * and "the pipeline never delivered" -- and the log alone cannot tell them
     * apart. This warning exists so the second reading is the default one. */
    if (CONFIG.zeroEventWarnMs > 0) {
        state.warnTimer = setTimeout(function () {
            if (state.following && state.nBB === 0 && state.nBLK === 0) {
                emit('WARN', 'zero events ' + CONFIG.zeroEventWarnMs +
                     'ms after follow (blocks=0 blk=0 calls=0) -- the pipeline is ' +
                     'NOT proven; do not report this as "the code did not run". ' +
                     'Control: follow a thread running a known loop first.');
            }
        }, CONFIG.zeroEventWarnMs);
    }

    if (CONFIG.followMs > 0) {
        state.timer = setTimeout(function () { endFollow('timeout'); },
                                 CONFIG.followMs);
    }
}

function endFollow(reason) {
    if (!state.following) return;
    state.following = false;
    if (state.timer !== null) { clearTimeout(state.timer); state.timer = null; }
    if (state.warnTimer) { clearTimeout(state.warnTimer); state.warnTimer = null; }
    try { Stalker.flush(); } catch (e) { /* already gone */ }
    try { Stalker.unfollow(state.followTid); } catch (e) { /* already gone */ }
    flush(true);
    emit('DONE', 'reason=' + reason + ' blocks=' + state.nBB +
         ' blk=' + state.nBLK + ' calls=' + state.nCALL +
         ' truncated=' + (state.truncated || reason === 'maxBlocks' ? 1 : 0));
}

/* ===================================================================
 * 4. triggers
 * =================================================================== */
function installTrigger() {
    var t = CONFIG.trigger || { kind: 'main' };
    state.target = Process.findModuleByName(CONFIG.targetModule);

    if (!state.target) {
        // Hardened apps and Flutter apps load their interesting library after
        // Application start; wait for the linker instead of failing.
        emit('TRIG-FAIL', 'module ' + CONFIG.targetModule + ' not loaded yet; ' +
             'hooking dlopen to wait for it');
        hookDlopen(CONFIG.targetModule, function (mod) {
            state.target = mod;
            armTrigger(t);
            emit('TRIG', 'module ' + mod.name + ' loaded at ' + mod.base +
                 '; trigger armed');
        });
        return;
    }
    armTrigger(t);
}

function armTrigger(t) {
    try {
        if (t.kind === 'export' || t.kind === 'offset') {
            var mod = Process.findModuleByName(t.module || CONFIG.targetModule);
            if (!mod) { emit('TRIG-FAIL', 'trigger module missing: ' + t.module); return; }
            var addr = null;
            if (t.kind === 'export') {
                addr = mod.findExport ? mod.findExport(t.export) : null;
                if (!addr) addr = Module.findExportByName(mod.name, t.export);
                if (!addr) {
                    emit('TRIG-FAIL', 'export not found: ' + mod.name + '!' + t.export);
                    return;
                }
            } else {
                addr = mod.base.add(t.offset || 0);
            }
            Interceptor.attach(addr, {
                onEnter: function () { beginFollow(this.threadId, 'trigger ' + addr); },
                onLeave: function () { endFollow('trigger-leave'); }
            });
            emit('TRIG', 'armed ' + t.kind + ' trigger at ' + addr);
        } else if (t.kind === 'java') {
            if (typeof Java === 'undefined') {
                emit('TRIG-FAIL', 'java trigger requested but no Java bridge; ' +
                     'align host frida and frida-server to the same 16.x');
                return;
            }
            Java.perform(function () {
                var Klass;
                try { Klass = Java.use(t.cls); }
                catch (e) { emit('TRIG-FAIL', 'class not found: ' + t.cls); return; }
                var hit = false;
                var names = t.method instanceof Array ? t.method : [t.method];
                for (var i = 0; i < names.length && !hit; i++) {
                    var ov = Klass[names[i]];
                    if (!ov || !ov.overloads) continue;
                    ov.overloads.forEach(function (o) {
                        // implementations run on the calling thread, so the
                        // current thread id IS the java->native boundary thread
                        o.implementation = function () {
                            beginFollow(Process.getCurrentThreadId(),
                                        'java ' + t.cls + '.' + names[i]);
                            try {
                                return o.apply(this, arguments);
                            } finally { endFollow('trigger-leave'); }
                        };
                    });
                    hit = true;
                }
                if (hit) emit('TRIG', 'armed java trigger ' + t.cls + '#' + names.join(','));
                else emit('TRIG-FAIL', 'method not found on ' + t.cls + ': ' + names.join(','));
            });
        } else if (t.kind === 'main') {
            if (CONFIG.autoStart === false) {
                emit('TRIG', 'main trigger armed (autoStart=false); call start()');
                return;
            }
            var tid = null;
            try { tid = Process.getMainThreadId(); } catch (e) { /* older gum */ }
            if (!tid || tid <= 0) {
                // getMainThreadId may not exist on older gum; on Android the
                // first thread frida lists is the process's main thread.
                var threads = Process.enumerateThreads();
                tid = threads.length ? threads[0].id : Process.getCurrentThreadId();
            }
            beginFollow(tid, 'main-thread follow (pid=' + Process.id + ')');
        } else {
            emit('TRIG-FAIL', 'unknown trigger kind: ' + t.kind);
        }
    } catch (e) {
        emit('TRIG-FAIL', String(e));
    }
}

/* Wait for a library the dynamic linker has not mapped yet. */
function hookDlopen(basename, onLoaded) {
    var seen = false;
    ['dlopen', 'android_dlopen_ext'].forEach(function (name) {
        var a = Module.findExportByName(null, name);
        if (!a) return;
        Interceptor.attach(a, {
            onEnter: function (args) {
                var p = args[0];
                this.path = (p && !p.isNull()) ? p.readCString() : null;
            },
            onLeave: function (res) {
                if (seen || !this.path) return;
                if (this.path.indexOf(basename) === -1) return;
                var mod = Process.findModuleByName(basename);
                if (mod) { seen = true; onLoaded(mod); }
            }
        });
    });
}

/* ===================================================================
 * 5. runtime control: rpc.exports + post('cfg')
 * =================================================================== */
rpc.exports = {
    config: function (patch) {
        if (!patch || typeof patch !== 'object')
            return { ok: false, error: 'config needs an object' };
        for (var k in patch) {
            if (k === 'trigger' && patch.trigger && typeof patch.trigger === 'object') {
                CONFIG.trigger = patch.trigger;
            } else if (k === 'events' && patch.events) {
                for (var e in patch.events) CONFIG.events[e] = !!patch.events[e];
            } else {
                CONFIG[k] = patch[k];
            }
        }
        // a re-config that changes WHAT we trace must not race the old follow
        if (state.following &&
            (patch.trigger !== undefined || patch.targetModule !== undefined ||
             patch.autoStart !== undefined)) {
            endFollow('reconfig');
        }
        installTrigger();
        return { ok: true, config: CONFIG };
    },
    start: function (argTid) {
        var tid = argTid || null;
        if (!tid || tid <= 0) {
            // never follow the rpc thread: it sleeps while waiting for us and
            // produces an empty trace. Prefer the process's main thread.
            try { tid = Process.getMainThreadId(); } catch (e) { /* older gum */ }
            if (!tid || tid <= 0) {
                var threads = Process.enumerateThreads();
                tid = threads.length ? threads[0].id : Process.getCurrentThreadId();
            }
        }
        beginFollow(tid, 'start-rpc');
        return { following: state.following, followingTid: tid };
    },
    stop: function () { endFollow('stop-rpc'); return status(); },
    status: function () { return status(); }
};

function status() {
    return {
        following: state.following,
        targetLoaded: !!state.target,
        target: state.target ? state.target.name : CONFIG.targetModule,
        seq: state.seq, blocks: state.nBB, blk: state.nBLK, calls: state.nCALL
    };
}

try {
    recv('cfg', function onCfg(message, payload) {
        rpc.exports.config(payload);
        recv('cfg', onCfg);              // stay armed for further updates
    });
} catch (e) { /* recv unavailable in this runtime; constants mode still works */ }

/* ===================================================================
 * 6. go
 * =================================================================== */
state.started = true;
// safety flush so lines emitted before/after a follow still reach the host
setInterval(function () { flush(true); }, 500);
emit('READY', 'stalker_trace loaded; target=' + CONFIG.targetModule +
     ' trigger=' + JSON.stringify(CONFIG.trigger) + ' followMs=' + CONFIG.followMs +
     ' maxBlocks=' + CONFIG.maxBlocks +
     ' moduleLoaded=' + !!Process.findModuleByName(CONFIG.targetModule));
installTrigger();
