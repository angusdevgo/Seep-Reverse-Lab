import org.jf.dexlib2.DexFileFactory;
import org.jf.dexlib2.Opcode;
import org.jf.dexlib2.Opcodes;
import org.jf.dexlib2.iface.ClassDef;
import org.jf.dexlib2.iface.Method;
import org.jf.dexlib2.iface.MethodImplementation;
import org.jf.dexlib2.builder.MutableMethodImplementation;
import org.jf.dexlib2.immutable.ImmutableMethod;
import org.jf.dexlib2.writer.pool.DexPool;

import java.io.File;
import java.util.ArrayList;
import java.util.List;

/**
 * dexlib2 定点 patch：把指定方法的实现整体替换为 return-void（或 return 常量）。
 *
 * 为什么不用 baksmali/smali 整树往返：实测在一个多 dex 应用上，整树往返重建后运行时报
 *   IncompatibleClassChangeError: Found interface io.ktor.client.engine.HttpClientEngine,
 *   but class was expected
 * （R8 生成的 synthetic access bridge 被破坏）。本工具只改目标方法的 code_item，
 * 其余类/方法/字符串表原样保留，因此不会有这类损伤。
 *
 * 用法: java PatchMethod <in.dex> <out.dex> <descriptor> <methodName> <returnType>
 *   例: java PatchMethod classes7.dex out.dex Lx6; d V
 */
public class PatchMethod {

    public static void main(String[] args) throws Exception {
        if (args.length < 5) {
            System.err.println("usage: PatchMethod <in.dex> <out.dex> <descriptor> <methodName> <returnType>");
            System.exit(2);
        }
        String inPath = args[0], outPath = args[1], desc = args[2], mName = args[3], ret = args[4];

        org.jf.dexlib2.iface.DexFile dex =
                DexFileFactory.loadDexFile(new File(inPath), Opcodes.forApi(34));

        List<ClassDef> outClasses = new ArrayList<ClassDef>();
        int patched = 0;

        for (ClassDef cd : dex.getClasses()) {
            List<Method> direct = new ArrayList<Method>();
            for (Method m : cd.getDirectMethods()) direct.add(m);
            List<Method> virtual = new ArrayList<Method>();
            for (Method m : cd.getVirtualMethods()) virtual.add(m);
            boolean isTargetClass = cd.getType().equals(desc);
            boolean changed = false;

            if (isTargetClass) {
                for (int pass = 0; pass < 2; pass++) {
                    List<Method> list = (pass == 0) ? direct : virtual;
                    for (int i = 0; i < list.size(); i++) {
                        Method m = list.get(i);
                        if (!m.getName().equals(mName) || !m.getReturnType().equals(ret)) continue;
                        // 用 return-void 替换整个方法体。
                        // 寄存器数必须保留原值：Compose/协程方法体里可能仍被其它指令引用同一寄存器窗口，
                        // 且 dex 校验要求 registers >= 参数寄存器数。
                        int regs = m.getImplementation() != null ? m.getImplementation().getRegisterCount() : 0;
                        MethodImplementation impl = new org.jf.dexlib2.immutable.ImmutableMethodImplementation(
                                regs,
                                java.util.Collections.singletonList(
                                        new org.jf.dexlib2.immutable.instruction.ImmutableInstruction10x(Opcode.RETURN_VOID)),
                                null,
                                null);
                        Method nm = new ImmutableMethod(
                                m.getDefiningClass(), m.getName(), m.getParameters(), m.getReturnType(),
                                m.getAccessFlags(), m.getAnnotations(), m.getHiddenApiRestrictions(),
                                impl);
                        list.set(i, nm);
                        patched++;
                        changed = true;
                        System.out.println("[patch] " + desc + "->" + mName + m.getReturnType()
                                + "  registers=" + regs);
                    }
                }
            }

            if (!changed) {
                outClasses.add(cd);
            } else {
                outClasses.add(new org.jf.dexlib2.immutable.ImmutableClassDef(
                        cd.getType(), cd.getAccessFlags(), cd.getSuperclass(),
                        cd.getInterfaces(), cd.getSourceFile(), cd.getAnnotations(),
                        cd.getStaticFields(), cd.getInstanceFields(), direct, virtual));
            }
        }

        DexFileFactory.writeDexFile(outPath,
                new org.jf.dexlib2.immutable.ImmutableDexFile(Opcodes.forApi(34), outClasses));
        System.out.println("[done] patched=" + patched + " -> " + outPath);
        if (patched == 0) {
            System.err.println("[warn] no method matched!");
            System.exit(1);
        }
    }
}
