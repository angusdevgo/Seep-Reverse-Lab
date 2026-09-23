// Minimal Frida probe: neutralise ONE native death site in memory, then report PATCHED.
//
// Intended for use with spawn_patch_detach.py. The write lands while attached; the
// driver then detaches so the app runs with no instrumentation present and its UI
// actually renders. Memory.patchCode writes survive detach; Interceptor hooks do not.
//
// Configure the four constants below from your own analysis. There is nothing
// target-specific here on purpose: the shape to look for is a short "recover the frame
// and return" epilogue that replaces a terminate call. Never substitute a NOP for a
// call that has live code after it -- the fall-through is the bug you are creating.
// See references/native-tamper-and-suicide.md.
'use strict';

// --- configure -----------------------------------------------------------------
var MODULE_NAME = 'libtarget.so';   // the module that holds the site
var FILE_OFFSET = 0x0;              // byte offset of the sequence to replace
var PATCH_BYTES = [];               // equal-length replacement bytes
var PRE_EXISTING = '';              // hex of PATCH_BYTES, space separated, for the idempotence check
// -------------------------------------------------------------------------------

var T0 = Date.now();
function el() { return ((Date.now() - T0) / 1000).toFixed(2) + 's'; }

function hx(p, n) {
    try {
        return Array.from(new Uint8Array(p.readByteArray(n))).map(function (b) {
            return ('0' + b.toString(16)).slice(-2);
        }).join(' ');
    } catch (e) { return '<unreadable>'; }
}

if (!PATCH_BYTES.length) {
    console.log('[!] PATCH_BYTES is empty -- configure this probe before using it');
    send('PATCHFAIL');
} else {
    var timer = setInterval(function () {
        var m = null;
        try { m = Process.findModuleByName(MODULE_NAME); } catch (e) { m = null; }
        if (!m) return;
        clearInterval(timer);

        var at = m.base.add(FILE_OFFSET);
        var before = hx(at, PATCH_BYTES.length);
        console.log('[' + el() + '][i] ' + MODULE_NAME + ' base=' + m.base +
                    ' bytes@0x' + FILE_OFFSET.toString(16) + ' = ' + before);

        if (PRE_EXISTING && before === PRE_EXISTING) {
            console.log('[' + el() + '][i] already carries the patch');
            send('PATCHED');
            return;
        }
        try {
            Memory.patchCode(at, PATCH_BYTES.length, function (code) {
                code.writeByteArray(PATCH_BYTES);
            });
            console.log('[' + el() + '][PATCH] now = ' + hx(at, PATCH_BYTES.length));
            send('PATCHED');
        } catch (e) {
            console.log('[' + el() + '][!] patch failed: ' + e);
            send('PATCHFAIL');
        }
    }, 10);
}

// Keep the message channel alive so the driver can see the probe is loaded. Cheap, and
// it gives a heartbeat you can read while waiting for the site to appear.
setInterval(function () { console.log('[' + el() + '][alive]'); }, 10000);

console.log('=== patch-only probe armed ===');
