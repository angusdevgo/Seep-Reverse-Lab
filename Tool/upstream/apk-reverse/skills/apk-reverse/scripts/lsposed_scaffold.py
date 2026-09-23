#!/usr/bin/env python3
"""Scaffold a minimal LSPosed module project that builds without Gradle.

Why this exists
---------------
Repackaging a hardened APK is not always the right route. When the app is
integrity-checked, signature-derived, or simply cheaper to hook than to rebuild,
the deliverable becomes a *module* instead of a patched APK, and the first
obstacle is that every tutorial assumes Android Studio. This script writes the
smallest project that a plain ``javac`` + ``d8`` + ``aapt2`` + ``apksigner``
chain can turn into an installable module, and the README it writes contains
that exact chain.

What it writes
--------------
    <out>/AndroidManifest.xml        the three xposed meta-data keys LSPosed reads
    <out>/assets/xposed_init         one line: the fully qualified entry class
    <out>/src/<pkg path>/<Class>.java  the entry class (IXposedHookLoadPackage)
    <out>/README.md                  build, install, enable, verify, failure modes

The generated hook does two things on purpose, because both are diagnostics
before they are features: it logs on every load of a scoped process (so
"is the module injected at all" is answerable from logcat alone), and it hooks
``Application.attach`` / ``Activity.onCreate`` (so the log names the real
Activity classes even when a packer swaps the Application at runtime).

Note on scope: LSPosed decides *which* processes to inject into from the scope
list in its own configuration, not from anything this project declares. A
generated ``TARGETS`` array is a second gate inside the module and must not be
mistaken for the scope.

Usage
-----
    lsposed_scaffold.py --package com.example.probe --name "Example probe" \\
        --hook-target com.example.target --out ./module

Requirements: python3 only. No third-party imports, no network.
"""
import argparse
import os
import re
import sys

MANIFEST_TMPL = """<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android"
    package="__PACKAGE__">

    <uses-sdk android:minSdkVersion="__MINSDK__" android:targetSdkVersion="__TARGETSDK__" />

    <application android:label="__NAME__" android:hasCode="true">
        <!-- These three keys are what LSPosed Manager reads. Without
             xposedmodule=true the APK installs as an ordinary app and never
             appears in the module list at all. xposedminversion=82 is the
             classic XposedBridge API level and is accepted by LSPosed. -->
        <meta-data android:name="xposedmodule" android:value="true" />
        <meta-data android:name="xposeddescription" android:value="__DESC__" />
        <meta-data android:name="xposedminversion" android:value="82" />
    </application>
</manifest>
"""

JAVA_TMPL = """package __PACKAGE__;

import android.app.Activity;
import android.app.Application;
import android.content.Context;
import android.os.Bundle;

import de.robv.android.xposed.IXposedHookLoadPackage;
import de.robv.android.xposed.XC_MethodHook;
import de.robv.android.xposed.XposedBridge;
import de.robv.android.xposed.XposedHelpers;
import de.robv.android.xposed.callbacks.XC_LoadPackage;

/**
 * Entry class named by assets/xposed_init.
 *
 * Logcat is the evidence channel: LSPosed pushes XposedBridge.log() into the
 * system log, so `adb logcat -s __TAG__` answers "did this module get injected"
 * without attaching a debugger.
 */
public class __CLASS__ implements IXposedHookLoadPackage {

    /** Short enough to stay readable in logcat. */
    private static final String TAG = "__TAG__";

    /**
     * In-module gate, NOT the LSPosed scope. LSPosed already decides which
     * processes receive handleLoadPackage; this array only keeps the hook body
     * from acting on unintended processes if the scope is widened later.
     */
    private static final String[] TARGETS = new String[] { __TARGETS__ };

    private static boolean isTarget(String pkg) {
        for (String t : TARGETS) {
            if (t.equals(pkg)) {
                return true;
            }
        }
        return false;
    }

    @Override
    public void handleLoadPackage(final XC_LoadPackage.LoadPackageParam lpp) throws Throwable {
        // Fires once per scoped process, before any of the app's own code runs.
        // This single line is the injection proof: if it is absent for a
        // process you scoped, the problem is scope/enable state or the target
        // process was never restarted, not your hook body.
        try {
            XposedBridge.log(TAG + " injected: " + lpp.packageName
                    + "/" + lpp.processName + " cl=" + shortCl(lpp.classLoader));
        } catch (Throwable t) {
            XposedBridge.log(t);
        }

        if (!isTarget(lpp.packageName)) {
            return;
        }

        // 1) Application.attach(Context) runs before the app's onCreate. Under a
        //    packer thisObject is the stub Application, not the manifest name.
        try {
            XposedHelpers.findAndHookMethod(Application.class, "attach", Context.class,
                    new XC_MethodHook() {
                        @Override
                        protected void afterHookedMethod(MethodHookParam param) throws Throwable {
                            XposedBridge.log(TAG + " Application.attach -> "
                                    + safeClass(param.thisObject));
                        }
                    });
            XposedBridge.log(TAG + " hook installed: Application.attach");
        } catch (Throwable t) {
            XposedBridge.log(TAG + " attach-hook FAILED: " + t);
        }

        // 2) Activity lifecycle. Boot-classloader targets, so these install even
        //    when the app's own classes are not yet resolvable.
        try {
            XposedHelpers.findAndHookMethod(Activity.class, "onCreate", Bundle.class,
                    new XC_MethodHook() {
                        @Override
                        protected void afterHookedMethod(MethodHookParam param) throws Throwable {
                            XposedBridge.log(TAG + " Activity.onCreate -> "
                                    + safeClass(param.thisObject));
                        }
                    });
            XposedBridge.log(TAG + " hook installed: Activity.onCreate");
        } catch (Throwable t) {
            XposedBridge.log(TAG + " activity-hook FAILED: " + t);
        }
__HOOK_BLOCK__
    }

    private static String safeClass(Object o) {
        try {
            return o == null ? "null" : o.getClass().getName();
        } catch (Throwable t) {
            return "<class-name-threw " + t.getClass().getSimpleName() + ">";
        }
    }

    private static String shortCl(ClassLoader cl) {
        try {
            if (cl == null) {
                return "null";
            }
            return cl.getClass().getName() + "@"
                    + Integer.toHexString(System.identityHashCode(cl));
        } catch (Throwable t) {
            return "<cl-threw>";
        }
    }
}
"""

HOOK_BLOCK_TMPL = """
        // 3) Replace this with the method you actually care about. Find it at
        //    runtime first (enumerate loaded classes / read a stack) rather than
        //    guessing an obfuscated name from a decompiler.
        try {
            XposedHelpers.findAndHookMethod("__HOOKCLASS__", lpp.classLoader,
                    "__HOOKMETHOD__", __PARAMTYPES__,
                    new XC_MethodHook() {
                        @Override
                        protected void beforeHookedMethod(MethodHookParam param) throws Throwable {
                            XposedBridge.log(TAG + " __HOOKCLASS__.__HOOKMETHOD__ entered");
                        }
                    });
            XposedBridge.log(TAG + " hook installed: __HOOKCLASS__.__HOOKMETHOD__");
        } catch (Throwable t) {
            XposedBridge.log(TAG + " target-hook FAILED: " + t);
        }
"""

README_TMPL = """# __NAME__

Minimal LSPosed module generated by `lsposed_scaffold.py`.

- module package: `__PACKAGE__`
- entry class: `__PACKAGE__.__CLASS__` (named in `assets/xposed_init`)
- in-module target gate: __TARGETLIST__
- minSdk __MINSDK__ / targetSdk __TARGETSDK__

The LSPosed *scope* is separate from the target gate above: scope is configured
in LSPosed Manager, and a module is injected into a process only when the scope
contains that package **and** the module is enabled.

## Build without Gradle

You need a JDK (17 works), Android build-tools, an `android.jar` for the SDK you
declare, and the Xposed API stub jar (`de.robv.android.xposed:api:82`, about
25 KB). Set the three variables, then run the steps in order. There is no
resource to compile; the module ships only a manifest, assets and a dex.

```sh
BT=/path/to/build-tools/34.0.0
AJ=/path/to/android.jar            # e.g. platforms/android-28/android.jar
API=/path/to/api-82.jar
OUT=build

# 1. Java -> class files. -source/-target 8 keeps d8 happy; Android API classes
#    come from -cp, not from the JDK. (`-bootclasspath` is gone in JDK 9+.)
javac -encoding UTF-8 -source 8 -target 8 -nowarn \\
    -cp "$AJ:$API" -d "$OUT/classes" src/__PATH__/__CLASS__.java

# 2. d8 wants a jar, NOT a directory -- a directory dies with
#    "Unsupported source file type".
jar cf "$OUT/classes.jar" -C "$OUT/classes" .
"$BT/d8" --min-api __MINSDK__ --lib "$AJ" --output "$OUT" "$OUT/classes.jar"

# 3. manifest + assets -> base apk (no res/ in this project)
"$BT/aapt2" link -o "$OUT/base.apk" -I "$AJ" \\
    --manifest AndroidManifest.xml \\
    --min-sdk-version __MINSDK__ --target-sdk-version __TARGETSDK__ \\
    -A assets

# 4. add the dex. aapt resolves the path relative to the cwd and stores the same
#    name, so run it from $OUT with classes.dex sitting there.
cp "$OUT/base.apk" "$OUT/unsigned.apk"
cp "$OUT/classes.dex" "$OUT/classes.dex.tmp" && mv "$OUT/classes.dex.tmp" "$OUT/classes.dex"
(cd "$OUT" && "$BT/aapt" add unsigned.apk classes.dex)

# 5. align, then sign (v2 is enough for Android 7+)
"$BT/zipalign" -f -p 4 "$OUT/unsigned.apk" "$OUT/aligned.apk"
keytool -genkeypair -keystore "$OUT/test.keystore" -alias mod -keyalg RSA \\
    -keysize 2048 -validity 10000 -storepass android -keypass android \\
    -dname "CN=module, O=local"
"$BT/apksigner" sign --ks "$OUT/test.keystore" --ks-pass pass:android \\
    --key-pass pass:android --v2-signing-enabled true \\
    --out "$OUT/module.apk" "$OUT/aligned.apk"
"$BT/apksigner" verify --print-certs "$OUT/module.apk"
```

Windows: same steps; `d8`, `apksigner` and `aapt` ship as `.bat` wrappers, and
the classpath separator is `;`. Note that `jar` and `keytool` are frequently
**not** on `PATH` even when `javac` is (Oracle's `javapath` shim exposes only
`java`/`javac`), so call them from the JDK's `bin` directory explicitly.

## Install, enable, verify

```sh
adb install -r build/module.apk
adb shell pm list packages | grep __PACKAGE__          # installed
adb shell dumpsys package __PACKAGE__ | grep enabled   # enabled=0 means DISABLED by the PM
adb shell pm enable __PACKAGE__                        # only if it shows enabled=0
```

`pm enable` is about the *package manager* state; it is not the LSPosed module
switch. Then, in LSPosed Manager: open the module list, enable the module, and
tick the scope entry for the target package.

Verification has two channels. Use the platform log where it works, and always the module log:

```sh
adb -s <serial> shell "su -c 'cat /data/adb/lspd/log/modules_<timestamp>.log'"   # module log
adb -s <serial> logcat -s __TAG__                                                # platform log
```

Expected first line in either: `__TAG__ injected: <target>/<process> ...`. The platform log can be
**completely empty** on a device whose `logd` route is broken (a log file that opens with
`Logd maybe crashed (err=Socket operation on non-socket)` is the tell); the module log is written
either way, so check it before concluding the module never ran. No line in either channel means the
module was not injected into that process. Check, in this order: module
enabled in LSPosed Manager, package present in scope, module APK still installed,
and **the target process restarted after the scope change** -- scope changes are
read for newly forked processes, so a running process keeps the old decision.

## Failure modes worth knowing

- `d8` on a directory: `Unsupported source file type`. Jar the classes first.
- `aapt add` says the file is missing: it resolves relative to the cwd and keeps
  the given name, so `classes.dex` must exist in the directory you run it from.
- Module never appears in LSPosed Manager: the `xposedmodule` meta-data is
  missing or mistyped in the merged manifest.
- Module listed but injection logs never appear: enabled state, scope, or a stale
  target process -- in that order.
- Module injected but your `TARGETS` array skips everything: that is the in-module
  gate, not LSPosed. Read the gate before blaming the framework.
"""


def build_parser():
    p = argparse.ArgumentParser(
        prog="lsposed_scaffold.py",
        description="Write a minimal, Gradle-free LSPosed module project "
                    "(manifest, xposed_init, entry class, build README).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Example:\n"
               "  lsposed_scaffold.py --package com.example.probe \\\n"
               "      --name \"Example probe\" --hook-target com.example.target \\\n"
               "      --hook-class com.example.target.Helper --hook-method check \\\n"
               "      --out ./module\n")
    p.add_argument("--package", required=True,
                   help="module package name, e.g. com.example.probe")
    p.add_argument("--name", required=True,
                   help="human-readable module name shown in LSPosed Manager")
    p.add_argument("--hook-target", action="append", default=None, dest="targets",
                   help="package the module acts on; repeat for several. "
                        "This is the in-module gate, not the LSPosed scope")
    p.add_argument("--out", required=True, help="output project directory")
    p.add_argument("--class-name", default="MainHook",
                   help="entry class name (default %(default)s)")
    p.add_argument("--tag", default=None,
                   help="logcat tag; default derived from --class-name (max 20 chars)")
    p.add_argument("--description", default="Hook module generated by lsposed_scaffold.py",
                   help="value of xposeddescription")
    p.add_argument("--min-sdk", type=int, default=24, help="minSdkVersion (default %(default)s)")
    p.add_argument("--target-sdk", type=int, default=28, help="targetSdkVersion (default %(default)s)")
    p.add_argument("--hook-class", default=None,
                   help="optional concrete class to hook (adds a worked example block)")
    p.add_argument("--hook-method", default=None,
                   help="method name to hook (requires --hook-class)")
    p.add_argument("--hook-params", default="",
                   help="comma-separated parameter types for --hook-method, "
                        "e.g. 'java.lang.String,android.content.Context' (default: none)")
    p.add_argument("--force", action="store_true",
                   help="overwrite files that already exist in --out")
    return p


PKG_RE = re.compile(r'^[a-zA-Z][a-zA-Z0-9_]*(\.[a-zA-Z][a-zA-Z0-9_]*)+$')
CLASS_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')


def fail(msg):
    print("[!] %s" % msg, file=sys.stderr)
    return 2


def write_file(path, text, force):
    if os.path.exists(path) and not force:
        print("[=] exists, left alone: %s" % path)
        return False
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    # newline="\n" so a scaffold written on Windows still builds on POSIX
    with open(path, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(text)
    print("[+] %s" % path)
    return True


def params_java(spec):
    """'java.lang.String,android.content.Context' -> 'java.lang.String.class,
    android.content.Context.class'."""
    parts = [x.strip() for x in spec.split(',') if x.strip()]
    if not parts:
        return ''
    return ', '.join('%s.class' % x for x in parts)


def main(argv=None):
    args = build_parser().parse_args(argv)

    if not PKG_RE.match(args.package):
        return fail("--package %r is not a valid Java package name" % args.package)
    if not CLASS_RE.match(args.class_name):
        return fail("--class-name %r is not a valid Java identifier" % args.class_name)
    targets = args.targets or ['<target.package>']
    for t in targets:
        if not PKG_RE.match(t) and t != '<target.package>':
            return fail("--hook-target %r is not a valid package name" % t)
    if args.hook_method and not args.hook_class:
        return fail("--hook-method requires --hook-class")

    tag = args.tag or args.class_name.upper()[:20]

    hook_block = ''
    if args.hook_class and args.hook_method:
        hook_block = (HOOK_BLOCK_TMPL
                      .replace('__HOOKCLASS__', args.hook_class)
                      .replace('__HOOKMETHOD__', args.hook_method)
                      .replace('__PARAMTYPES__', params_java(args.hook_params)))

    java = (JAVA_TMPL
            .replace('__PACKAGE__', args.package)
            .replace('__CLASS__', args.class_name)
            .replace('__TAG__', tag)
            .replace('__TARGETS__', ', '.join('"%s"' % t for t in targets))
            .replace('__HOOK_BLOCK__', hook_block))

    manifest = (MANIFEST_TMPL
                .replace('__PACKAGE__', args.package)
                .replace('__NAME__', args.name)
                .replace('__DESC__', args.description)
                .replace('__MINSDK__', str(args.min_sdk))
                .replace('__TARGETSDK__', str(args.target_sdk)))

    readme = (README_TMPL
              .replace('__NAME__', args.name)
              .replace('__PACKAGE__', args.package)
              .replace('__CLASS__', args.class_name)
              .replace('__TAG__', tag)
              .replace('__PATH__', args.package.replace('.', '/'))
              .replace('__TARGETLIST__', ', '.join('`%s`' % t for t in targets))
              .replace('__MINSDK__', str(args.min_sdk))
              .replace('__TARGETSDK__', str(args.target_sdk)))

    src = os.path.join(args.out, 'src', args.package.replace('.', os.sep),
                       '%s.java' % args.class_name)
    write_file(os.path.join(args.out, 'AndroidManifest.xml'), manifest, args.force)
    write_file(os.path.join(args.out, 'assets', 'xposed_init'),
               '%s.%s\n' % (args.package, args.class_name), args.force)
    write_file(src, java, args.force)
    write_file(os.path.join(args.out, 'README.md'), readme, args.force)

    print("")
    print("Next: build it with the chain in %s/README.md, then install, enable"
          " the module in LSPosed Manager, and add the target to its scope."
          % args.out)
    print("Do not confuse the scope (LSPosed Manager) with the in-module gate"
          " (TARGETS in %s.java)." % args.class_name)
    return 0


if __name__ == '__main__':
    sys.exit(main())
