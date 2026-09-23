# 逆向模式汇编打桩速查字典

> 来源：softseep 主控 §二 | 加载时机：需要具体汇编打桩指令模式时


| 目标场景 | 机器码序列 | 汇编指令 | 适用场景与安全特性 |
| :--- | :--- | :--- | :--- |
| **虚函数整型返回 1** | `b0 01 c3` | `mov al, 1; ret` | 3 字节，零栈破坏，适合 UI 判决虚函数 |
| **通用函数整型返回 1** | `b8 01 00 00 00 c3` | `mov eax, 1; ret` | 6 字节，清空高位，适合标准 Cdecl/Fastcall 标量接口 |
| **永久有效时间戳** | `b8 7f e6 85 f4` | `mov eax, 0xf485e67f` | 5 字节，硬件清零 RAX 高位，返回 2099-12-31 |
| **条件跳转强制直通** | `90 90` / `eb <disp>` | `nop; nop` / `jmp short` | 2 字节，消除校验失败跳转 |
| **长跳转跳过逻辑块** | `e9 <disp32> 90` | `jmp near <target>; nop` | 5~6 字节，跳过弹窗、试用拦截或广告拉取 |
| **BSTR 截断绕过** | `ff 25 [disp32]` | `jmp qword ptr [SysAllocString]` | 尾调用 IAT，自平衡栈且无 Double Free |
| **IAT 输出 API 挂钩** | 改写 IAT 槽位指针 | `*slot = Hook_Proc` | 零字节落盘、零 ABI 风险，适用显示层文案伪造 |
| **IAT 槽位恢复** | `*slot = realProc` | `VirtualProtect` + 回写 | 卸载钩子 / 规避自检，需先缓存原地址 |

---
