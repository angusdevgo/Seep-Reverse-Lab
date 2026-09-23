# seep — AI-Native 逆向工程与攻防 MCP Server

`seep` 是面向安全研究员与 AI Agent（Pi Agent、Claude、Cursor、OpenCode、VS Code 等）的混合型逆向工程与 CTF 战术 MCP Server。

它将 Radare2 二进制逆向套件、JADX / Apktool 安卓反编译链、动态 Hook 生成器与 ReverseLab 183+ 攻防战术知识库聚合为一个标准 MCP 服务。

---

## 核心能力与 Tools 列表

### 1. 状态与环境
- `seep_status`：一键检测 radare2、JADX、Apktool、Java、Python 及 ReverseLab 知识库就绪状态。

### 2. 二进制逆向 (Radare2 跨架构引擎)
- `seep_r2_info`：提取 PE / ELF / Mach-O 架构、位数、大小端、编译器及保护机制（Canary, NX, PIE, RELRO, ASLR）。
- `seep_r2_cmd`：执行自定义 radare2 分析命令（支持 `aaa; afl`, `pdf @ main`, `iz`, `px 64 @ 0x...` 等）。
- `seep_r2_strings`：提取数据段或全段字符串，支持关键词过滤与截断控制。
- `seep_r2_functions`：列出二进制函数列表、导入导出符号与入口点。
- `seep_r2_disasm`：反汇编指定函数或虚拟地址（包含交叉引用、源码行号与调用关系）。
- `seep_r2_decompile`：将目标函数一键反编译为类 C 伪代码。
- `seep_r2_diff`：利用 radiff2 进行双二进制差异比对（代码比对 `-C` / 十六进制比对 `-x` / 统计摘要 `-s`）。
- `seep_r2_asm`：汇编机器码或将十六进制指令反汇编为汇编代码。

### 3. Android APK 逆向与动态 Hook 生成
- `seep_apk_info`：免 Java 原生解析 APK 压缩包（统计 DEX、Native .so 架构、签名并提取 Manifest 核心特征）。
- `seep_apk_decompile`：调用内置 JADX 将 APK / DEX 还原为 Java 源码工程（支持混淆还原）。
- `seep_apk_unpack`：调用内置 Apktool 解包资源、清晰明文 Manifest 及 Smali 代码。
- `seep_apk_smali_search`：在 Smali 或源码工程中极速检索加解密密钥、Token、API 路由及安全验证逻辑。
- `seep_apk_gen_hook`：自动根据类名与方法签名生成 Frida (JavaScript) 或 LSPilot / BeanShell 动态 Hook 插件。

### 4. ReverseLab 攻防知识库与 CTF Payload 库
- `seep_kb_search`：在 183+ 篇攻防知识库（Web/PE/APK/CVE/内核）中进行全文检索并输出高分推荐。
- `seep_kb_read`：读取任意技术手册或实战指南全文。
- `seep_kb_checklist`：获取《Web CTF 前 30 分钟应急排查指南》、全攻击矩阵、证据链标准等战术清单。
- `seep_kb_payloads`：快速调取高危 Exploit 种子与 Payload（JWT, SSRF, 原型链污染, SSTI, SQLi, 反序列化等）。

---

## 客户端配置指南

### 1. Pi Agent（已自动配置）
已写入 `C:\Users\Angus\.pi\agent\mcp.json`：
```json
{
  "mcpServers": {
    "seep": {
      "command": "python",
      "args": [
        "C:\\Users\\Angus\\Desktop\\pi\\seep\\seep_mcp_server.py"
      ],
      "env": {
        "PYTHONIOENCODING": "utf-8"
      },
      "transport": "stdio"
    }
  }
}
```

### 2. Claude Desktop / Claude Code
在 `claude_desktop_config.json` 或 `settings.json` 中添加：
```json
{
  "mcpServers": {
    "seep": {
      "command": "python",
      "args": ["C:/Users/Angus/Desktop/pi/seep/seep_mcp_server.py"]
    }
  }
}
```

### 3. Cursor / OpenCode / VS Code
在 MCP 客户端配置中直接指定可执行程序 `python`，参数为 `C:\Users\Angus\Desktop\pi\seep\seep_mcp_server.py`，传输方式选 `stdio`。

---

## 验证与测试

在终端运行内置单元测试验证所有工具：
```bash
python test_seep_mcp.py
```
全部 9 个测试套件通过即表示 MCP Server 运行正常。
