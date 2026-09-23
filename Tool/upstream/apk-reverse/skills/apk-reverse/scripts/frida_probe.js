/*
 * frida_probe.js -- four-layer full-chain network probe for a hardened Android app.
 *
 * WHY THIS SHAPE
 * --------------
 * When you cannot tell why a request never reaches the server (or why it fails
 * silently), a single-layer hook always leaves you guessing. This script hooks
 * FOUR independent layers at once, so *whichever* layer the app actually uses
 * produces evidence:
 *
 *   [APP]    the app's own network wrapper class(es)   -> what business method asked
 *   [OKHTTP] OkHttp full chain                         -> newCall/build/execute/async/proceed
 *   [RAW-URL] java.net.URL.openConnection              -> HttpsURLConnection, which uses the
 *                                                         SYSTEM trust store and therefore
 *                                                         fails differently from OkHttp
 *   [THROW]  java.lang.Throwable.getMessage            -> recovers the exception text that an
 *                                                         upper layer swallowed with catch {}
 *
 * The RAW-URL vs OKHTTP distinction is the single most valuable signal here: an app
 * commonly has two unrelated trust chains, so "login fails but browsing works" is
 * explained by which of the two fired. See LESSONS G3.
 *
 * Every hook is installed inside its own try/catch. One missing class (a different
 * OkHttp major version, a renamed obfuscated class) never disables the other three
 * layers. Failures are reported as HOOK-FAIL lines instead of killing the script.
 *
 * ADAPT TO YOUR TARGET (only this block matters)
 * ---------------------------------------------
 *   1) APP_NET_CLASSES  -> replace with the app's own network wrapper class name(s)
 *   2) APP_PKG_PREFIX   -> the app's package prefix, used only to filter noise
 *   3) ENABLE_* flags   -> turn layers off if they are too noisy
 * Everything else is target-independent.
 *
 * HOW TO RUN
 * ----------
 *   Prefer the bundled injector, which also writes a log file and stays resident:
 *       python run_probe.py frida_probe.js 10 --pkg com.example.app
 *   Or by hand against a remote device:
 *       frida -H 127.0.0.1:27042 -p <pid> -l frida_probe.js
 *
 * OUTPUT FORMAT
 * -------------
 *   Every line is  <ISO-ish local timestamp> <TAG> <key=value ...>
 *   TAGS: READY | HOOK-FAIL | FATAL | APP | OKHTTP-NEWCALL | OKHTTP-BUILD |
 *         OKHTTP-EXEC | OKHTTP-ASYNC | OKHTTP-PROCEED | RAW-URL | DNS | THROW
 *   Add STACK to a line only where a call chain is genuinely useful (APP, RAW-URL),
 *   because it is the expensive part.
 */

/* ===================================================================
 * 1. ADAPT THESE LINES
 * =================================================================== */
// The app's own network wrapper / API helper class(es). Enumerate ALL declared
// methods at runtime, so you do not have to know the obfuscated method names.
// Example: 'com.example.app.net.HttpHelper', 'com.example.app.api.ApiClient'
var APP_NET_CLASSES = ['com.example.app.net.HttpHelper'];

// Used only to filter THROW noise: messages from classes whose name contains this
// prefix are always kept. Leave as-is if you do not care.
var APP_PKG_PREFIX = 'com.example.app';

// Layer switches. Turn a layer off if it produces more noise than signal.
var ENABLE_APP = true;        // [APP]     app's own wrapper classes (needs APP_NET_CLASSES)
var ENABLE_OKHTTP = true;     // [OKHTTP]  OkHttp newCall/build/execute/AsyncCall/proceed
var ENABLE_RAW_URL = true;    // [RAW-URL] java.net.URL.openConnection (HttpsURLConnection)
var ENABLE_THROWABLE = true;  // [THROW]   Throwable.getMessage, deduplicated
var ENABLE_DNS = true;        // [DNS]     InetAddress.getAllByName, one line per unique host
var STACK_ON_APP = true;      // attach a stack to [APP] hits
var STACK_ON_RAW_URL = true;  // attach a stack to [RAW-URL] hits
var STACK_LINES = 12;         // how many stack frames to keep

// Safety valves: this probe must never become the thing that kills the app.
var MAX_STRING = 3000;        // truncate any single value
var THROWABLE_MAX_LINES = 400;// hard cap on THROW lines
var THROWABLE_STACK = false;  // stacks on every Throwable line are usually too much

/* ===================================================================
 * 2. Plumbing (target-independent)
 * =================================================================== */

function pad(n, w) {
  var s = '' + n;
  while (s.length < w) s = '0' + s;
  return s;
}

// Local wall-clock with milliseconds. Local, not UTC, because you will be
// comparing these lines against logcat and your own shell history.
function stamp() {
  var d = new Date();
  return d.getFullYear() + '-' + pad(d.getMonth() + 1, 2) + '-' + pad(d.getDate(), 2) + ' ' +
         pad(d.getHours(), 2) + ':' + pad(d.getMinutes(), 2) + ':' + pad(d.getSeconds(), 2) + '.' +
         pad(d.getMilliseconds(), 3);
}

function str(v, max) {
  if (v === null) return 'null';
  if (v === undefined) return 'undefined';
  var s;
  try { s = '' + v; } catch (e) { s = '<unprintable>'; }
  max = max || MAX_STRING;
  if (s.length > max) s = s.substring(0, max) + '...<+' + (s.length - max) + ' chars>';
  return s;
}

function sendLine(tag, fields) {
  var parts = [];
  if (fields) {
    for (var k in fields) {
      if (!fields.hasOwnProperty(k)) continue;
      if (fields[k] === null || fields[k] === undefined || fields[k] === '') continue;
      parts.push(k + '=' + str(fields[k]));
    }
  }
  var line = { t: stamp(), tag: tag, msg: parts.join(' ') };
  try { send(line); } catch (e) { /* transport gone; nothing sane to do */ }
}

// Call-chain capture. Expensive, so it is opt-in per hook.
function stackText(lines) {
  try {
    var Log = Java.use('android.util.Log');
    var Throwable = Java.use('java.lang.Throwable');
    var full = Log.getStackTraceString(Throwable.$new());
    var rows = ('' + full).split('\n');
    var kept = [];
    // Drop the probe's own frames at the top; they are never the interesting part.
    for (var i = 0; i < rows.length && kept.length < (lines || STACK_LINES); i++) {
      if (rows[i].indexOf('frida') >= 0) continue;
      if (rows[i].indexOf('java.lang.Throwable') >= 0) continue;
      if (rows[i].indexOf('android.util.Log') >= 0) continue;
      kept.push(rows[i].replace(/^\s+/, ''));
    }
    return kept.join(' <- ');
  } catch (e) {
    return '<stack unavailable: ' + e + '>';
  }
}

// The whole point: a failure to install one hook must not affect the others.
function guard(label, fn) {
  try {
    fn();
    return true;
  } catch (e) {
    sendLine('HOOK-FAIL', { where: label, err: e });
    return false;
  }
}

// Run one whole layer and return how many hooks it really installed.
//   > 0  that many hooks are live
//   = 0  the layer installed nothing (its classes were not found); NOT a success
//   =-1  the layer is switched off in the config header
// Returning a count instead of a boolean matters: a layer whose classes are absent
// still returns normally (each inner hook catches its own error), so a boolean
// "did not throw" would report a layer as installed when it hooked nothing at all.
function runLayer(label, fn) {
  try {
    return fn();
  } catch (e) {
    sendLine('HOOK-FAIL', { where: 'install ' + label, err: e });
    return 0;
  }
}

/* ===================================================================
 * 3. Layer [APP]: the app's own network wrapper
 * =================================================================== */
// Why getDeclaredMethods: obfuscated wrappers routinely expose the same name with
// several overloads, and a decompiler's short names (a, b, c) are not reliable
// enough to enumerate by hand. Enumerate at runtime, wrap each overload, and let
// the stack tell you which one the business code called.
// Build a replacement of a fixed arity that reports the hit and then delegates.
//
// Two deliberate choices here, both about not breaking the app:
//  * The original is NOT cached in a variable. Frida does not hand out the pre-hook
//    implementation through `overload.implementation` (it is undefined until you
//    replace it), so `var orig = ov.implementation; ... orig.apply(...)` would
//    throw a TypeError on the first real call and propagate straight into the app's
//    network path. Calling the same name on `this` from inside the replacement is
//    the documented way to reach the original, and it re-resolves the overload from
//    the runtime argument types.
//  * The delegate call is written out per arity instead of spread/apply, so no
//    engine-specific behaviour is involved. Methods with more than 8 parameters are
//    reported and left alone rather than bound incorrectly.
function appReplacement(className, methodName, arity) {
  var label = className + '.' + methodName;
  var note = function (argc) {
    sendLine('APP', {
      call: label,
      argc: argc,
      stack: STACK_ON_APP ? stackText() : null
    });
  };
  switch (arity) {
    case 0: return function () {
      note(arguments.length); return this[methodName]();
    };
    case 1: return function (a0) {
      note(arguments.length); return this[methodName](a0);
    };
    case 2: return function (a0, a1) {
      note(arguments.length); return this[methodName](a0, a1);
    };
    case 3: return function (a0, a1, a2) {
      note(arguments.length); return this[methodName](a0, a1, a2);
    };
    case 4: return function (a0, a1, a2, a3) {
      note(arguments.length); return this[methodName](a0, a1, a2, a3);
    };
    case 5: return function (a0, a1, a2, a3, a4) {
      note(arguments.length); return this[methodName](a0, a1, a2, a3, a4);
    };
    case 6: return function (a0, a1, a2, a3, a4, a5) {
      note(arguments.length); return this[methodName](a0, a1, a2, a3, a4, a5);
    };
    case 7: return function (a0, a1, a2, a3, a4, a5, a6) {
      note(arguments.length); return this[methodName](a0, a1, a2, a3, a4, a5, a6);
    };
    case 8: return function (a0, a1, a2, a3, a4, a5, a6, a7) {
      note(arguments.length); return this[methodName](a0, a1, a2, a3, a4, a5, a6, a7);
    };
    default: return null;
  }
}

function installAppLayer() {
  if (!ENABLE_APP) return -1;
  if (!APP_NET_CLASSES.length) {
    sendLine('HOOK-FAIL', { where: 'APP', err: 'APP_NET_CLASSES is empty; edit the header' });
    return 0;
  }
  var wrappedTotal = 0;
  APP_NET_CLASSES.forEach(function (className) {
    guard('APP ' + className, function () {
      var Cls = Java.use(className);
      var declared = Cls.class.getDeclaredMethods();
      var total = declared.length;
      var wrapped = 0;
      var skipped = 0;
      for (var i = 0; i < total; i++) {
        (function (idx) {
          var methodName;
          try { methodName = '' + declared[idx].getName(); } catch (e) { return; }
          guard('APP ' + className + '.' + methodName, function () {
            var overloads = Cls[methodName];
            if (!overloads || !overloads.overloads) return;
            overloads.overloads.forEach(function (ov) {
              var argTypes;
              try { argTypes = ov.argumentTypes; } catch (e) { argTypes = null; }
              var arity = (argTypes && typeof argTypes.length === 'number') ? argTypes.length : -1;
              var label = className + '.' + methodName + '(' + (argTypes ? argTypes.join(',') : '?') + ')';
              guard('APP bind ' + label, function () {
                var replacement = appReplacement(className, methodName, arity);
                if (replacement === null) {
                  skipped++;
                  sendLine('APP', {
                    call: label,
                    skipped: 'arity ' + arity + ' exceeds 8; left unwrapped on purpose'
                  });
                  return;
                }
                ov.implementation = replacement;
                wrapped++;
              });
            });
          });
        })(i);
      }
      wrappedTotal += wrapped;
      sendLine('APP', {
        call: className,
        declared_methods: total,
        overloads_wrapped: wrapped,
        overloads_skipped: skipped
      });
    });
  });
  return wrappedTotal;
}

/* ===================================================================
 * 4. Layer [OKHTTP]: the whole OkHttp chain
 * =================================================================== */
// Five independent anchors on purpose. Any single one can be missing depending on
// the OkHttp major version and on R8 inlining, and each still answers a different
// question:
//   newCall      -> a request object reached OkHttp (earliest reliable URL)
//   build        -> the URL existed even if the call was never executed
//   execute      -> synchronous call actually ran, with status code and duration
//   AsyncCall.run-> asynchronous call actually ran (enqueue path)
//   proceed      -> every actual network step, including redirects and retries
function installOkHttpLayer() {
  if (!ENABLE_OKHTTP) return -1;

  var installed = 0;
  var can = function (label, fn) { if (guard(label, fn)) installed++; };

  can('OKHTTP newCall', function () {
    var Client = Java.use('okhttp3.OkHttpClient');
    Client.newCall.overload('okhttp3.Request').implementation = function (req) {
      var url = '<unknown>';
      try { url = '' + req.url().toString(); } catch (e) { url = '<url error: ' + e + '>'; }
      sendLine('OKHTTP-NEWCALL', { url: url });
      return this.newCall(req);
    };
  });

  can('OKHTTP Request$Builder.build', function () {
    var Builder = Java.use('okhttp3.Request$Builder');
    Builder.build.implementation = function () {
      var req = this.build();
      var url = '<unknown>';
      try { url = '' + req.url().toString(); } catch (e) { url = '<url error: ' + e + '>'; }
      sendLine('OKHTTP-BUILD', { url: url });
      return req;
    };
  });

  can('OKHTTP RealCall.execute', function () {
    var RealCall = Java.use('okhttp3.internal.connection.RealCall');
    RealCall.execute.implementation = function () {
      var url = '<unknown>';
      try { url = '' + this.request().url().toString(); } catch (e) { url = '<url error: ' + e + '>'; }
      var t0 = Date.now();
      var resp = this.execute();
      var code = '?';
      try { code = '' + resp.code(); } catch (e) { code = '<code error>'; }
      sendLine('OKHTTP-EXEC', { url: url, ms: Date.now() - t0, code: code });
      return resp;
    };
  });

  can('OKHTTP RealCall$AsyncCall.run', function () {
    var AsyncCall = Java.use('okhttp3.internal.connection.RealCall$AsyncCall');
    AsyncCall.run.implementation = function () {
      // The URL is not reliably reachable from here across OkHttp versions; the
      // newCall/build hooks above supply it. This hook proves *when* the async
      // path actually started and finished, which is what matters for timing.
      var t0 = Date.now();
      this.run();
      sendLine('OKHTTP-ASYNC', { phase: 'done', ms: Date.now() - t0 });
    };
  });

  can('OKHTTP RealInterceptorChain.proceed', function () {
    var Chain = Java.use('okhttp3.internal.http.RealInterceptorChain');
    Chain.proceed.overload('okhttp3.Request').implementation = function (req) {
      var url = '<unknown>';
      try { url = '' + req.url().toString(); } catch (e) { url = '<url error: ' + e + '>'; }
      var t0 = Date.now();
      var resp = this.proceed(req);
      var code = '?';
      try { code = '' + resp.code(); } catch (e) { code = '<code error>'; }
      sendLine('OKHTTP-PROCEED', { url: url, ms: Date.now() - t0, code: code });
      return resp;
    };
  });
  return installed;
}

/* ===================================================================
 * 5. Layer [RAW-URL]: HttpsURLConnection -> the SYSTEM trust store
 * =================================================================== */
// Many apps route login/registration through java.net.URL.openConnection instead
// of OkHttp. That path validates against the system trust store, so an expired or
// untrusted server certificate breaks it while the OkHttp path keeps working.
// If this layer fires but the OkHttp layer stays silent, you are on the other
// trust chain -- check the certificate out-of-band with tls_check.py.
function installRawUrlLayer() {
  if (!ENABLE_RAW_URL) return -1;

  var URL;
  try {
    URL = Java.use('java.net.URL');
  } catch (e) {
    sendLine('HOOK-FAIL', { where: 'RAW-URL java.net.URL', err: e });
    return 0;
  }
  var installed = 0;
  var can = function (label, fn) { if (guard(label, fn)) installed++; };

  can('RAW-URL openConnection()', function () {
    // Report AFTER the original returns, so we can also name the concrete connection
    // class (HttpURLConnection vs HttpsURLConnection) -- that distinction is what
    // tells you which trust chain the request is about to use.
    // As in the APP layer, the original is reached via `this.openConnection(...)`
    // rather than a cached function reference.
    URL.openConnection.overload().implementation = function () {
      var url = '<unknown>';
      try { url = '' + this.toString(); } catch (e) { url = '<url error: ' + e + '>'; }
      var conn = this.openConnection();
      var connCls = '?';
      try { connCls = '' + conn.getClass().getName(); } catch (e) { connCls = '<class error>'; }
      sendLine('RAW-URL', {
        url: url,
        kind: 'no-arg',
        conn: connCls,
        stack: STACK_ON_RAW_URL ? stackText() : null
      });
      return conn;
    };
  });

  can('RAW-URL openConnection(Proxy)', function () {
    URL.openConnection.overload('java.net.Proxy').implementation = function (proxy) {
      var url = '<unknown>';
      try { url = '' + this.toString(); } catch (e) { url = '<url error: ' + e + '>'; }
      var conn = this.openConnection(proxy);
      var connCls = '?';
      try { connCls = '' + conn.getClass().getName(); } catch (e) { connCls = '<class error>'; }
      sendLine('RAW-URL', {
        url: url,
        kind: 'proxy',
        conn: connCls,
        stack: STACK_ON_RAW_URL ? stackText() : null
      });
      return conn;
    };
  });
  return installed;
}

/* ===================================================================
 * 6. Layer [THROW]: recover swallowed exception text
 * =================================================================== */
// An upper-layer `catch (Exception e) { }` hides exactly the message you need.
// Hooking Throwable.getMessage is the cheapest way to get it back, but it is a
// very hot method, so: only concrete Exception/Error subclasses, deduplicated by
// class+message, hard-capped, and stacks off by default.
function installThrowableLayer() {
  if (!ENABLE_THROWABLE) return -1;

  // Returns 1 only when the hook is really bound to the runtime.
  return guard('THROWABLE getMessage', function () {
    var seen = {};
    var printed = 0;
    var suppressed = 0;
    var Throwable = Java.use('java.lang.Throwable');

    Throwable.getMessage.implementation = function () {
      var msg;
      try {
        msg = this.getMessage();
      } catch (e) {
        return null;
      }
      try {
        var cls = '' + this.getClass().getName();
        var looksLikeError = (cls.indexOf('Exception') >= 0 || cls.indexOf('Error') >= 0);
        var isAppClass = (cls.indexOf(APP_PKG_PREFIX) === 0);
        if (looksLikeError || isAppClass) {
          var key = cls + '|' + msg;
          if (seen[key]) {
            seen[key]++;
          } else if (printed < THROWABLE_MAX_LINES) {
            seen[key] = 1;
            printed++;
            sendLine('THROW', {
              cls: cls,
              msg: msg,
              stack: THROWABLE_STACK ? stackText() : null
            });
          } else {
            suppressed++;
            if (suppressed === 1 || suppressed % 200 === 0) {
              sendLine('THROW', { note: 'cap reached, further unique messages suppressed', printed: printed });
            }
          }
        }
      } catch (e) {
        // Never let the reporting path throw: this hook is on a very hot path.
      }
      return msg;
    };
  }) ? 1 : 0;
}

/* ===================================================================
 * 7. Optional layer [DNS]: which hosts the app really resolves
 * =================================================================== */
// Cheap, high-signal: if an SDK's domains are never resolved, that subsystem never
// started -- much stronger evidence than "logcat was quiet". Deduplicated per host
// so a retry loop cannot flood the log.
function installDnsLayer() {
  if (!ENABLE_DNS) return -1;

  return guard('DNS getAllByName', function () {
    var seen = {};
    var Inet = Java.use('java.net.InetAddress');
    Inet.getAllByName.overload('java.lang.String').implementation = function (host) {
      var first = false;
      try {
        var key = '' + host;
        if (!seen[key]) { seen[key] = 1; first = true; }
      } catch (e) { /* ignore */ }
      if (first) sendLine('DNS', { host: host });
      return this.getAllByName(host);
    };
  }) ? 1 : 0;
}

/* ===================================================================
 * 8. Boot
 * =================================================================== */
var JAVA_BRIDGE_HINT =
    'align the host frida package and the on-device frida-server to the same 16.x version; ' +
    '17.x can fail to locate the Android dynamic linker and removes the built-in Java bridge';

function main() {
  if (typeof Java === 'undefined' || Java === null) {
    // frida 17+ removed the built-in Java bridge.
    sendLine('FATAL', {
      err: 'Java bridge is not available in this frida runtime',
      fix: JAVA_BRIDGE_HINT
    });
    return;
  }
  // Java.perform can fail BEFORE the callback ever runs: on a non-Android host, and
  // on frida 17.x, where it throws "Java API not available". Without this catch the
  // whole script dies as an opaque `type: error` message with a stack pointing into
  // frida-java-bridge, which tells you nothing about the version mismatch that
  // actually caused it.
  try {
    Java.perform(function () {
      var installed = [];
      var failed = [];
      var disabled = [];
      [
        ['APP', installAppLayer],
        ['OKHTTP', installOkHttpLayer],
        ['RAW-URL', installRawUrlLayer],
        ['THROW', installThrowableLayer],
        ['DNS', installDnsLayer]
      ].forEach(function (pair) {
        var count = runLayer(pair[0], pair[1]);
        if (count === -1) disabled.push(pair[0]);
        else if (count > 0) installed.push(pair[0] + ':' + count);
        else failed.push(pair[0]);
      });
      sendLine('READY', {
        installed: installed.join(',') || 'none',
        failed: failed.join(',') || 'none',
        disabled: disabled.join(',') || 'none',
        note: 'hooks are live; now drive the app UI'
      });
      if (failed.length) {
        sendLine('READY-HINT', {
          failed: failed.join(','),
          fix: 'a layer reporting 0 hooks means its classes were not found: the app may '
             + 'not use that library, R8 may have renamed the class, or the classloader '
             + 'differs. Layers that installed keep working -- debug the failed ones by '
             + 'their HOOK-FAIL line, not the working ones.'
        });
      }
    });
  } catch (e) {
    sendLine('FATAL', {
      err: 'Java.perform failed: ' + e,
      fix: JAVA_BRIDGE_HINT
    });
  }
}

// Last-resort net: any unexpected top-level error still leaves a readable line in
// the log instead of only a raw frida script error.
try {
  main();
} catch (e) {
  sendLine('FATAL', { err: 'probe aborted: ' + e, note: 'no hooks were installed' });
}
