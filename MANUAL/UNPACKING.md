# MANUAL — 通用脱壳前置分析 SOP (Unpacking & Deobfuscation)

> 本文件适用于 G0/G1 阶段识别出加壳保护后的标准化处置流程。
> 覆盖：MPRESS / UPX / Themida / VMP 3.x / .NET Reactor / 自定义混淆。
> 原则：**能动态 dump 就不静态逆壳**，优先内存 Dump 重建，效率最高。

---

## 一、 壳类型速查与工具路由

| 壳特征（triage 输出信号）| 壳类型 | 首选脱壳路线 |
|---|---|---|
| `MPRESS1` / `MPRESS2` 节区节名 | MPRESS | 等待 OEP 后内存 dump（Scylla） |
| `UPX0` / `UPX1` 节名，入口在末节 | UPX | `upx -d target.exe` 直接命令行解压 |
| `themida`/`.Boot` 节名，大量无效导入 | Themida/WinLicense | OEP 断点 + Scylla IAT Rebuild |
| `.vmp0` / `.vmp1` 节名，VM bytecode | VMP 3.x | 内存 dump + 动态 trace 提取算法（见第四节）|
| 熵值 > 7.2（整个文件），无可读字符串 | 自定义壳 / 强加密 | rabin2 entropy + x64dbg 手动定位 OEP |
| `.text` 区段全 0、代码在 .rsrc 内 | 资源型 Loader | 提取资源区段 → 分析 Loader 落盘路径 |
| `_CorExeMain` 导入（.NET）| .NET 壳 | de4dot + dnSpy 优先，再看 VMP 字节码 |

---

## 二、 通用 OEP 定位 + 内存 Dump 流程（适用所有用户态壳）

### 步骤一：定位 OEP（原始入口点）

```text
策略 A（ESP 定律 — 通用于 MPRESS/UPX/简单 PE 壳）：
1. 在 x64dbg 中运行程序，在首个用户态断点暂停
2. 在 ESP（栈顶指针）处设置内存写入断点（Hardware BP on Write）
3. 运行至断点触发，此时 EIP 即为解压后的 OEP
4. 验证：OEP 处通常为 "push ebp; mov ebp, esp" 或 .NET CRT init 代码

策略 B（节区执行监控 — 通用于 Themida/自定义壳）：
1. 用 x64dbg 打开，在"内存布局"中对原始代码节区（.text）设置执行断点
2. 运行程序，壳在向 .text 写完解密代码后会 jmp 到 OEP，此时断点触发
3. 记录此时的 EIP 地址

策略 C（API 断点反向追踪 — 通用于所有壳）：
1. 在 GetCommandLineA / GetModuleHandleA 等 CRT 初始化必调 API 上设断点
2. 程序调用此 API 时已完成壳初始化，此时在调用栈中回溯到 OEP
```

### 步骤二：内存 Dump 与 IAT 重建

使用 **Scylla**（x64dbg 内置插件）：

```text
1. 在 OEP 处暂停后打开 Scylla（Plugins → Scylla）
2. OEP 自动填入，点击 "IAT Autosearch" 扫描导入表
3. 点击 "Get Imports" 获取完整 IAT
4. 对所有标记为无效（红色）的条目，点击 "Fix Dump" 尝试自动修复
5. 点击 "Dump" 导出内存映像
6. 点击 "Fix Dump" 将 IAT 写入 Dump 文件
7. 用 CFF Explorer 或 PE-bear 验证修复后的 PE 头完整性
```

---

## 三、 UPX 脱壳（最简单，一行命令）

```powershell
# 直接解压（破坏性操作，先备份！）
Copy-Item target.exe target_backup.exe
upx -d target.exe

# 验证解压成功
.\Tool\mcp\Tool\safe\radare2\bin\rabin2.exe -I target.exe | Select-String "class|bits|type"
```

若 UPX 头被抹除（修改魔数以对抗 `upx -d`）：

```python
# 修复被抹除的 UPX 魔数
with open("target.exe", "r+b") as f:
    data = f.read()
    # 定位 UPX 压缩数据特征并还原魔数
    idx = data.find(b"\x55\x58\x50\x00")  # UPX! 魔数附近
    if idx > 0:
        f.seek(idx - 4)
        f.write(b"UPX!")
print("Header patched, retry: upx -d target.exe")
```

---

## 四、 VMP 3.x 脱壳与算法提取（最复杂，动态 trace 优先）

> VMP 将原始 x86/x64 指令编译为自定义 VM 字节码，**不可能静态完整还原**。
> 正确策略：**不试图还原 VM 本身，而是在 VM 执行过程中 trace 算法结果**。

### 4.1 G0 阶段止损判定

```text
seep_auto_triage 检测到 .vmp0/.vmp1 节名后，Agent 应立即输出：
  "⚠️ 目标存在 VMP 3.x 级虚拟机保护，超出全自动符号反编译范畴。
   将切换为动态 trace 策略提取关键算法输出，而非还原完整伪代码。"
```

### 4.2 动态 Trace 策略（提取算法的输入/输出）

```javascript
// Frida 方案：监控 VMP 保护函数的入口参数与出口返回值
// 需先通过 auto_triage 确定被 VMP 保护的关键导出函数 RVA
const baseAddr = Process.enumerateModules()[0].base;
const vmProtectedFunc = baseAddr.add(0xDEAD00);  // 替换为实际 RVA

Interceptor.attach(vmProtectedFunc, {
  onEnter(args) {
    console.log("[VMP] Func entered, args:");
    for (let i = 0; i < 4; i++) {
      try { console.log(`  arg[${i}] = ${args[i]} = "${args[i].readUtf8String()}"`); }
      catch(e) { console.log(`  arg[${i}] = ${args[i]}`); }
    }
  },
  onLeave(retval) {
    console.log(`[VMP] Func returned: ${retval} (0x${retval.toString(16)})`);
  }
});
```

### 4.3 Unidbg 模拟执行（无需真机，黑盒调用）

```bash
# 适用于 Android SO 中的 VMP 保护（Java_* 导出函数）
# 在 Unidbg 中直接调用目标 JNI 函数，忽略内部 VM 实现，只捕获结果
java -jar unidbg-android.jar \
  --lib target.so \
  --func Java_com_example_MainActivity_verifyLicense \
  --args "test_user_id,TEST-SERIAL-1234"
```

---

## 五、 .NET 壳脱壳（.NET Reactor / ConfuserEx / Eazfuscator）

### 5.1 通用流程

```powershell
# 第一步：用 de4dot 自动识别并去混淆
.\de4dot.exe target.exe -o target_clean.exe

# 第二步：用 dnSpy 打开清理后的程序集检查
# 若 de4dot 无法识别，尝试：
.\de4dot.exe --dont-rename target.exe -o target_clean.exe
```

### 5.2 运行时 dump（对抗字符串/资源加密）

```javascript
// Frida 方案：在 .NET CLR System.Reflection.Assembly.Load 时捕获解密后的程序集
const Load = Module.getExportByName('clr.dll', '_CorExeMain');
// 等待 CLR 完成解密，dump AppDomain 中加载的所有程序集
Process.enumerateModules().forEach(m => {
  if (m.name.endsWith('.dll') || m.name.endsWith('.exe')) {
    console.log(`[CLR Module] ${m.name} @ ${m.base} size=${m.size}`);
    // 用 Memory.readByteArray 导出并 PE-fix
  }
});
```

---

## 六、 脱壳后完整性验证

```powershell
# 快速验证脱壳后 PE 是否可正常分析
$r2 = ".\Tool\mcp\Tool\safe\radare2\bin\rabin2.exe"

# 检查 PE 头完整性
& $r2 -I target_unpacked.exe | Select-String "class|type|bits|os|subsys"

# 检查导入表是否正常恢复
& $r2 -i target_unpacked.exe | head -20

# 检查节区属性（脱壳后 .text 应为 RX）
& $r2 -S target_unpacked.exe
```

---

## 七、 两击熔断纪律 —— 脱壳的止损规则

| 情形 | 触发 | 处置 |
|---|---|---|
| ESP 定律 2 次均找不到 OEP | 壳可能有 TLS 回调或多层包装 | 改用节区执行监控策略 |
| 节区执行监控 2 次失败 | 壳对内存断点有检测 | 改用 API 断点反向追踪 |
| 所有 Dump 策略失败 | 可能有内核级保护 | 声明"当前工具链无法完全脱壳"，切换 Unidbg Emulation 提取算法关键结果 |
