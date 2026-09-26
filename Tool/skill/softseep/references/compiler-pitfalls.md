# 编译器与平台契约陷阱清单（血泪教训）

> 来源：softseep 主控 §五 | 加载时机：写代理 DLL / 补丁工程前必读


### 陷阱 1：编译器吞掉 `\r` 与 `\x000D`（高危）

**现象**：宽字符串字面量 `L"...\r\n..."` 或 `L"...\x000D\x000A..."` 经 `zig-clang` 编译后，**二进制里只剩 `0A 00`，`0D` 消失**，导致 UI 长时间挤在一行。

**验证手段**：直接在编译产物的二进制里搜宽字符片段：
```python
data = open('version.dll','rb').read()
i = data.find('A\x00n\x00g\x00u\x00s\x00'.encode('latin1'))
print(' '.join('%02X'%b for b in data[i+20:i+30]))
# 期望 62 00 0D 00 0A 00（'b' + CR + LF）；若为 62 00 0A 00 则 CR 已被吞
```

**双保险解法**：
1. 字面量改用**通用字符名** `\u000D\u000A`（4 位定长，无编码歧义）；
2. 增加**运行时规范化**，抢在真实 API 之前修正：

```c
// LF -> CRLF, 孤立 CR -> CRLF, 已是 CRLF 则原样保留
static int NormalizeCrlf(const WCHAR* src, WCHAR* dst, int dstCap) {
    int o = 0;
    for (const WCHAR* p = src; *p; ++p) {
        if (*p == L'\r' || *p == L'\n') {
            if (o + 2 >= dstCap) break;
            dst[o++] = L'\r'; dst[o++] = L'\n';
            if (*p == L'\r' && p[1] == L'\n') ++p;
        } else {
            if (o + 1 >= dstCap) break;
            dst[o++] = *p;
        }
    }
    dst[o] = 0;
    return o;
}
```

**通用铁律**：凡涉及**平台敏感的字节级契约**（换行符 CRLF/LF、BOM、结构体对齐填充、字节序），**永不信任编译器字面量**，必须运行时兜底 + 二进制级验证。

### 陷阱 2：`vfprintf("%ls")` 遇非 ASCII 静默截断（高危）

**现象**：默认 C locale 下 `fprintf(fp, "orig='%ls'\n", wstr)` 一碰到第一个汉字就**当场截断并吃掉整行剩余输出**，让日志看起来像“代码没执行”。本次因此多走了数轮弯路。

**规避**：日志中所有非 ASCII 一律转 **UTF-16 码点十六进制**打印：
```c
char hexDump[1024] = {0}; int pos = 0;
for (int i = 0; i < 60 && s[i] && pos < 900; ++i)
    pos += sprintf(hexDump + pos, "%04X ", (unsigned int)s[i]);
LogToFile("[HOOK] -> REWRITE (%d chars) BYTES: %s\n", n, hexDump);
```

### 陷阱 3：Hook 未命中分支无日志

**现象**：因为控件类名白名单不匹配（静态推测 `Static`，实测为 `Edit`），挂钩静默不生效；日志只显示“被调用”却无“已重写”，严重误导排查方向。

**铁律**：**每一个 `if` 分支都必须留日志，包括 else 分支。**

### 陷阱 4：DLL 被运行中进程占用无法替换
**现象**：`Device or resource busy` / 复制失败。
**规避**：替换前必须 `Stop-Process -Name <target> -Force` 并等待句柄释放。

### 陷阱 5：权限不足写入 Program Files
**现象**：`Permission denied`。
**规避**：沙盒目录内完成全部验证，最终由用户以管理员权限落地。

### 陷阱 6：中文 `.bat` 写成 UTF-8 → 满屏「不是内部或外部命令」（高危）

**现象**：批处理里只要含中文 `echo`，双击运行就报一堆：
```
'锛屾垨鍏堝仛娓呭崟闄嶆潈' 不是内部或外部命令，也不是可运行的程序
'o.' 不是内部或外部命令，也不是可运行的程序
```
即中文变成**GBK 解码 UTF-8 字节**的典型乱码（`锛`/`垨` 等），且行尾引号/括号被吃掉，导致后半段被当成命令执行。

**根因**：`cmd.exe` 按**当前控制台代码页**（中文系统 = 936/GBK）解码批处理文件字节；
用 UTF-8（无论有无 BOM）保存即必然乱码。中途 `chcp 65001` **不可靠**（cmd 是边读边执行）。

**铁律**：
1. **中文 `.bat` 一律用 GBK(cp936) 保存，且不加 BOM**；
2. 关键命令行（`python xxx.py` / `powershell -File xxx.ps1`）**只写 ASCII**，中文仅出现在 `echo` 里；
3. 能用 `.ps1`（UTF-8 **with BOM**）或 `.py`（UTF-8）就**不要**用 `.bat`；
4. 自检脚本里加一条断言：`run_repro.bat` **不得含 UTF-8 BOM**。

```powershell
$bytes = [System.IO.File]::ReadAllBytes($bat)
$hasBom = ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF)
if ($hasBom) { throw 'must be GBK (cp936), not UTF-8 with BOM' }
```

### 陷阱 7：GUI 子进程继承控制台 → 控制台关闭时被连带杀掉（高危）

**现象**：补丁器/启动器（尤其 `.bat`）跑完、控制台窗口关闭后，**刚被拉起的 GUI 目标进程一起消失**；
表现为“目标窗口一闪就没了”、“bat 里明明启动成功了但进程不在”。

**根因**：`CreateProcess` 默认让子进程**继承父进程的控制台**。控制台关闭时，
所有附着该控制台的进程会收到 **`CTRL_CLOSE_EVENT`**，未注册控制台处理器的进程默认被终止。
（GUI 子系统程序不自己分配控制台，但**仍会继承**调用方的。）

**规避**：创建目标时加上 `CREATE_DETACHED_PROCESS`（`0x00000008`）使其彻底脱离控制台：

```python
CREATE_DETACHED_PROCESS = 0x00000008
k32.CreateProcessW(target, None, None, None, False,
                   CREATE_DETACHED_PROCESS, None, workdir,
                   ctypes.byref(si), ctypes.byref(pi))
```
```powershell
$CREATE_DETACHED_PROCESS = 0x00000008
[SBZPatcher]::CreateProcessW($Target, $null, [IntPtr]::Zero, [IntPtr]::Zero, $false,
    $CREATE_DETACHED_PROCESS, [IntPtr]::Zero, $cwd, [ref]$si, [ref]$pi)
```

**验证方法**：`.bat` 跑完后单独查一次进程存活：
```powershell
powershell -NoProfile -Command "(Get-Process -Name <name> -ErrorAction SilentlyContinue).Count"
# 期望 1；若为 0 则说明子进程被控制台关闭连带杀死
```

---
