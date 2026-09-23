# Windows 客户端复杂宿主内存热补丁与崩溃防御规范 (MuMu 实战提炼)

本规范提炼自网易 MuMu 模拟器（包含 `MuMuNxMain.exe` 前台界面进程与 `MuMuNxService.exe` 后台守护服务）客户端本地化实战，专门解决现代复杂 C++ 宿主（Qt / CEF / 多进程架构）在内存热补丁过程中常见的崩溃与失效难题。

---

## 1. C++ ABI 与 STL 容器内存不变量守则 (杜绝 0xC0000005 崩溃)

### 痛点根因
在逆向分析反汇编时，经常会将类似以下汇编代码误判为普通的 getter 函数：
```asm
mov rsi, [rcx+330h]
lea rdx, [rsp+0d0h]
call std::string::assign  ; 或者是向 std::map / std::unordered_map 中插入元素
```
如果直接将其函数头覆盖为 `mov eax, 1; ret` (`b8 01 00 00 00 c3`)：
- 该函数不会初始化调用方栈上的 `[rsp+0d0h]` 结构体指针；
- 后续流程把包含随机垃圾数据的指针传入 `std::map::insert` 或 STL 红黑树平衡算法；
- 宿主直接触发 `STATUS_ACCESS_VIOLATION 0xC0000005` 崩溃。

### 避坑规范
1. **纯标量拦截原则**：只改写纯标量整型读取接口（如读取 `int32` / `int64` 的 call），严禁改写复杂对象构造或字符串赋值函数。
2. **虚函数入口零栈破坏**：对于 UI 判决接口（如 `GetMemberType()`），使用 3 字节紧凑机器码：
   ```asm
   b0 01 c3   ; mov al, 1; ret
   ```
   不破坏 RSP 栈指针，不产生栈帧不平衡。

---

## 2. 三层协同覆盖决策体系 (防云端下发与离线回退)

针对现代具备云端同步能力的客户端，单一打桩点必然被云端下发覆盖或本地缓存回退破坏，必须同时覆盖三层：

| 层级 | 劫持点位 | 解决的核心问题 |
| :--- | :--- | :--- |
| **第一层：UI 决策层** | `GetMemberType()` 虚函数分支 | 解决冷启动瞬间 UI 徽标、试用提示与去广告开关的初始状态渲染 |
| **第二层：网络协议层** | HTTP/CEF 反序列化函数 (`0xd0e0d0` - `0xd0f550`) | 拦截云端下发的未付费 JSON 响应，在反序列化进入内存结构体瞬间重写整型字段 |
| **第三层：本地存储层** | `AccountManager` 本地 JSON / INI 读取函数 | 解决断网离线启动时从本地磁盘缓存读取过期状态导致的功能回退 |

---

## 3. 单次轻量工作线程 (One-Shot Clean Guard)

### 对抗传统死循环看门狗的缺陷
- 传统方案：`while (1) { Sleep(500); VirtualProtect(...); }`
- 缺陷：
  1. 频繁修改 `.text` 代码段属性为 `PAGE_EXECUTE_READWRITE`，宿主多线程并发执行到该页时极易产生访问冲突；
  2. 极易被 EDR / 杀软的内存行为启发式规则捕捉；
  3. 造成无意义的后台 CPU 占用。

### 标准实现范式
```c
DWORD WINAPI ApplyPatchesThread(LPVOID lpParam) {
    // 1. 等待主模块关键节区完全加载与解密
    Sleep(200);

    // 2. 识别当前宿主身份 (主进程 vs 服务进程)
    WCHAR modPath[MAX_PATH];
    GetModuleFileNameW(NULL, modPath, MAX_PATH);

    // 3. 执行单次批量打桩并恢复原保护属性
    DWORD oldProtect;
    VirtualProtect(target, size, PAGE_EXECUTE_READWRITE, &oldProtect);
    memcpy(target, patch_bytes, size);
    VirtualProtect(target, size, oldProtect, &oldProtect);

    // 4. 线程自然退出返回，零残留开销
    return 0;
}
```

---

## 4. x86_64 架构 64 位时间戳的 5 字节紧凑表达

在 x86_64 体系下，`mov eax, imm32` 会硬件自动清零 RAX 高 32 位：
```asm
b8 7f e6 85 f4   ; mov eax, 0xf485e67f
```
执行后 RAX 寄存器内容为 `0x00000000F485E67F`（即 `2099-12-31 23:59:59`），仅占用 5 字节，相比 `mov rax, imm64`（10 字节）更加安全小巧，不易越界破坏邻近代码。
