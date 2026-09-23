import org.jf.dexlib2.DexFileFactory;
import org.jf.dexlib2.Opcode;
import org.jf.dexlib2.Opcodes;
import org.jf.dexlib2.iface.ClassDef;
import org.jf.dexlib2.iface.Method;
import org.jf.dexlib2.iface.instruction.Instruction;
import org.jf.dexlib2.immutable.ImmutableClassDef;
import org.jf.dexlib2.immutable.ImmutableDexFile;
import org.jf.dexlib2.immutable.ImmutableMethod;
import org.jf.dexlib2.immutable.ImmutableMethodImplementation;
import org.jf.dexlib2.immutable.instruction.ImmutableInstruction11x;
import org.jf.dexlib2.immutable.instruction.ImmutableInstruction22c;
import org.jf.dexlib2.immutable.instruction.ImmutableInstruction35c;
import org.jf.dexlib2.immutable.instruction.ImmutableInstruction51l;
import org.jf.dexlib2.immutable.reference.ImmutableFieldReference;
import org.jf.dexlib2.immutable.reference.ImmutableMethodReference;

import java.io.File;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;

/**
 * dexlib2 surgical rewrites -- worked example: force one lambda's emit() to hand a
 * constant downstream instead of the value it read from its source.
 *
 * WHAT IT PATCHES
 *   <target>$$inlined$map$1$2.emit(Object, Continuation)Object
 *     -> send a fixed wide (long) constant to the downstream collector, unconditionally
 *
 * WHY THIS SHAPE
 *   Kotlin's `map { ... }` on a Flow compiles to a synthetic class whose emit()
 *   reads the source value from a field and forwards it to the collector. Replacing
 *   that single forwarding body turns "value read from the data source" into
 *   "constant", without touching the data source itself. Doing it in dex keeps the
 *   change inside the APK, so a fresh install behaves the same way -- writing the
 *   value into the app's runtime state instead would not survive a reinstall.
 *
 * ONE READ, ONE WRITE. Never rewrite the same dex twice in the same run: dexlib2
 * round-trips degrade an R8-optimized dex, and the second pass is where it shows.
 *
 * ADAPT TO YOUR TARGET
 *   java PatchMethodExample <in.dex> <out.dex> [targetClass] [fieldOwner:fieldName:fieldType]
 *                           [collectorIface] [continuationType]
 *   Every optional argument defaults to an obviously-fake example value below, and
 *   the effective values are printed at startup, so a run is never ambiguous.
 *
 * HOW TO FIND THE REAL VALUES
 *   * target class: search the dex strings for the source's field/data key, then read
 *     the call site with baksmali -- see scripts/dex_strings.py and scripts/find_refs.py.
 *   * collector iface / continuation type: read them off the emit() signature in smali.
 *     After R8 they are usually single letters; do not guess, copy them.
 *
 * DO NOT PATCH SHARED CODE BY ACCIDENT
 *   A generic card/image composable is commonly shared between ordinary content and
 *   ad slots. Turning such a method into `return-void` breaks normal rendering too.
 *   Before patching anything, count its callers (scripts/find_refs.py).
 */
public class PatchMethodExample {

    /** Synthetic class that owns the lambda: <Owner>$<member>$$inlined$map$1$2. */
    private static String TARGET_CLASS =
            "Lcom/example/app/data/ExampleStore$currentValue$$inlined$map$1$2;";

    /** The field on the lambda that holds the downstream collector. */
    private static String FIELD_OWNER = "Lcom/example/app/data/ExampleStore$currentValue$$inlined$map$1$2;";
    private static String FIELD_NAME = "b";
    private static String FIELD_TYPE = "Lcom/example/app/Collector;";

    /** The collector type and the Continuation type used by emit(). */
    private static String COLLECTOR_IFACE = "Lcom/example/app/Collector;";
    private static String CONTINUATION_TYPE = "Lkotlin/coroutines/Continuation;";

    private static final long CONSTANT = 4102444800000L;   // ~2100-01-01 (ms)

    private static void usage() {
        System.out.println("usage: PatchMethodExample <in.dex> <out.dex> "
                + "[targetClass] [fieldOwner:fieldName:fieldType] "
                + "[collectorIface] [continuationType]");
        System.out.println("  defaults (example values, replace for your target):");
        System.out.println("    targetClass      " + TARGET_CLASS);
        System.out.println("    fieldRef         " + FIELD_OWNER + ":" + FIELD_NAME + ":" + FIELD_TYPE);
        System.out.println("    collectorIface   " + COLLECTOR_IFACE);
        System.out.println("    continuationType " + CONTINUATION_TYPE);
    }

    private static void applyArgs(String[] args) {
        if (args.length > 2 && !args[2].isEmpty()) {
            TARGET_CLASS = args[2];
        }
        if (args.length > 3 && !args[3].isEmpty()) {
            String[] parts = args[3].split(":");
            if (parts.length != 3) {
                throw new IllegalArgumentException(
                        "fieldRef must be owner:name:type, got " + args[3]);
            }
            FIELD_OWNER = parts[0];
            FIELD_NAME = parts[1];
            FIELD_TYPE = parts[2];
        }
        if (args.length > 4 && !args[4].isEmpty()) {
            COLLECTOR_IFACE = args[4];
        }
        if (args.length > 5 && !args[5].isEmpty()) {
            CONTINUATION_TYPE = args[5];
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length < 2) {
            usage();
            System.exit(2);
        }
        applyArgs(args);

        String in = args[0], out = args[1];
        System.out.println("[in ] " + in);
        System.out.println("[cfg] targetClass=" + TARGET_CLASS);
        System.out.println("[cfg] fieldRef=" + FIELD_OWNER + ":" + FIELD_NAME + ":" + FIELD_TYPE);
        System.out.println("[cfg] collectorIface=" + COLLECTOR_IFACE);
        System.out.println("[cfg] continuationType=" + CONTINUATION_TYPE);
        System.out.println("[cfg] constant=" + CONSTANT);

        org.jf.dexlib2.iface.DexFile dex =
                DexFileFactory.loadDexFile(new File(in), Opcodes.forApi(34));

        List<ClassDef> outClasses = new ArrayList<ClassDef>();
        int patched = 0;

        for (ClassDef cd : dex.getClasses()) {
            List<Method> direct = new ArrayList<Method>();
            for (Method m : cd.getDirectMethods()) direct.add(m);
            List<Method> virtual = new ArrayList<Method>();
            for (Method m : cd.getVirtualMethods()) virtual.add(m);
            boolean touched = false;

            if (cd.getType().equals(TARGET_CLASS)) {
                for (int pass = 0; pass < 2; pass++) {
                    List<Method> list = (pass == 0) ? direct : virtual;
                    for (int i = 0; i < list.size(); i++) {
                        Method m = list.get(i);
                        if (!m.getName().equals("emit")
                                || !m.getReturnType().equals("Ljava/lang/Object;")
                                || m.getImplementation() == null) {
                            continue;
                        }
                        // Register layout for emit(Object, Continuation):
                        //   v0        scratch (return value)
                        //   v1:v2     the wide constant we build
                        //   v3 = p0   this (the lambda)
                        //   v4 = p1   the value being forwarded (ignored)
                        //   v5 = p2   the downstream Continuation
                        List<Instruction> body = new ArrayList<Instruction>();
                        body.add(new ImmutableInstruction22c(Opcode.IGET_OBJECT, 0, 3,
                                new ImmutableFieldReference(FIELD_OWNER, FIELD_NAME, FIELD_TYPE)));
                        body.add(new ImmutableInstruction51l(Opcode.CONST_WIDE, 1, CONSTANT));
                        body.add(new ImmutableInstruction35c(Opcode.INVOKE_STATIC, 2, 1, 2, 0, 0, 0,
                                new ImmutableMethodReference("Ljava/lang/Long;", "valueOf",
                                        Collections.singletonList("J"), "Ljava/lang/Long;")));
                        body.add(new ImmutableInstruction11x(Opcode.MOVE_RESULT_OBJECT, 1));
                        body.add(new ImmutableInstruction35c(Opcode.INVOKE_INTERFACE, 3, 0, 1, 5, 0, 0,
                                new ImmutableMethodReference(COLLECTOR_IFACE, "emit",
                                        Arrays.asList("Ljava/lang/Object;", CONTINUATION_TYPE),
                                        "Ljava/lang/Object;")));
                        body.add(new ImmutableInstruction11x(Opcode.MOVE_RESULT_OBJECT, 0));
                        body.add(new ImmutableInstruction11x(Opcode.RETURN_OBJECT, 0));

                        list.set(i, new ImmutableMethod(m.getDefiningClass(), m.getName(),
                                m.getParameters(), m.getReturnType(), m.getAccessFlags(),
                                m.getAnnotations(), m.getHiddenApiRestrictions(),
                                new ImmutableMethodImplementation(6, body, null, null)));
                        patched++;
                        touched = true;
                        System.out.println("[patch] emit -> constant=" + CONSTANT
                                + " (list=" + pass + ")");
                    }
                }
            }

            if (!touched) {
                outClasses.add(cd);
            } else {
                outClasses.add(new ImmutableClassDef(
                        cd.getType(), cd.getAccessFlags(), cd.getSuperclass(), cd.getInterfaces(),
                        cd.getSourceFile(), cd.getAnnotations(), cd.getStaticFields(),
                        cd.getInstanceFields(), direct, virtual));
            }
        }

        DexFileFactory.writeDexFile(out, new ImmutableDexFile(Opcodes.forApi(34), outClasses));
        System.out.println("[out ] " + out + "  patched=" + patched);
        if (patched == 0) {
            // The usual causes: wrong target class (R8 renamed it), the method is not
            // emit(Object,Continuation), or the class is not in THIS dex.
            System.err.println("[fail] target not found in this dex. Check: the exact "
                    + "TARGET_CLASS descriptor, that emit(Object,Continuation) exists there, "
                    + "and that you loaded the dex that actually contains this class.");
            System.exit(1);
        }
    }
}
