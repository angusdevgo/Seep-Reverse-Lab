// rpc_template.js — editable rpc.exports example for frida_rpc_serve.py.
//
// Three shapes every target needs, already wired:
//   1. add      — a pure-JS export, proves the transport with zero target knowledge
//   2. getpackagename — a harmless Java probe (calls a framework method via JNI)
//   3. callnative — a native-call placeholder: wrap any exported symbol of any
//                  loaded module and call it with explicit types
//
// Adapt 3 to your target: the hardened .so that computes a signature or an
// encryption is usually either exported (Module.findExportByName) or bound at
// runtime via RegisterNatives (hook RegisterNatives first to learn the address,
// then pass the raw address to callnativeaddr).

'use strict';

function log(ev, data) {
  try { send(Object.assign({ t: Date.now(), ev: ev }, data || {})); } catch (e) {}
}

// Export lookup that works across frida 16/17 (Module.findExportByName(null,..)
// was removed in 17; getGlobalExportByName is the replacement).
function resolveExport(name) {
  try { if (Module.getGlobalExportByName) return Module.getGlobalExportByName(name); } catch (e) {}
  try { if (Module.findExportByName) return Module.findExportByName(null, name); } catch (e) {}
  try {
    const libc = Process.findModuleByName('libc.so');
    if (libc) return libc.getExportByName(name);
  } catch (e) {}
  return null;
}

rpc.exports = {
  // 1) pure-JS demo — sanity-check the RPC transport itself.
  add: function (a, b) {
    return a + b;
  },

  ping: function () {
    return 'pong';
  },

  // 2) harmless Java probe: the package name of the process we live in.
  //    Works on any app process with a live Java VM; needs no target knowledge.
  getpackagename: function () {
    let out = null;
    Java.perform(function () {
      const app = Java.use('android.app.ActivityThread').currentApplication();
      out = app.getPackageName();
    });
    return out;
  },

  // 3) NATIVE CALL PLACEHOLDER — adapt module/name/ret/arg types to your target.
  //    moduleName null means "search every loaded module" (global export lookup).
  callnative: function (moduleName, exportName, retType, argTypes, args) {
    let addr = null;
    if (moduleName) {
      const base = Module.findBaseAddress(moduleName);
      if (base === null) throw new Error('module not loaded: ' + moduleName);
      addr = Module.findExportByName(moduleName, exportName);
    } else {
      addr = resolveExport(exportName);
    }
    if (addr === null) throw new Error('export not found: ' + exportName);
    const fn = new NativeFunction(addr, retType, argTypes);
    return fn.apply(null, args || []);
  },

  // Variant for symbols that never hit the export table (dynamically registered
  // JNI, or an offset inside a stripped .so): pass module name + raw offset.
  callnativeaddr: function (moduleName, offset, retType, argTypes, args) {
    const base = Module.findBaseAddress(moduleName);
    if (base === null) throw new Error('module not loaded: ' + moduleName);
    const fn = new NativeFunction(base.add(offset), retType, argTypes);
    return fn.apply(null, args || []);
  }
};

log('RPC-READY', { exports: Object.keys(rpc.exports) });
