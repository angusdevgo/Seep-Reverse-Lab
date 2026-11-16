# NixOS / Home Manager

The flake provides a package, an stdio MCP server, a development shell, and a
Home Manager module for `x86_64-linux`. Enable Nix flakes and
`nix-command` before using these commands.

## Run or install

```bash
# Start the stdio MCP server (normally launched by your MCP client).
nix run github:angusdevgo/Seep-Reverse-Lab

# Install seep-reverse-lab and the seep-mcp alias.
nix profile add github:angusdevgo/Seep-Reverse-Lab

# From a clone, enter a shell with Python + mcp and the native toolchain.
nix develop
python Tool/mcp/seep_mcp_server.py
```

Nix supplies Python with `mcp`, Radare2, JDK 17, JADX, Apktool, Node.js and unzip.
The installed package replaces the bundled JADX launcher and Apktool jar with
Nix package paths. Its files are read-only under
`<package>/share/seep-reverse-lab`; keep analysis inputs and outputs in a writable
working directory. No system pip installation or FHS compatibility layer is
needed for the packaged server and core toolchain.

For an MCP client using the usual JSON format:

```json
{
  "mcpServers": {
    "seep": {
      "command": "seep-mcp",
      "args": []
    }
  }
}
```

The client must inherit the Nix profile's PATH, or use the absolute package path
to `bin/seep-mcp`.

## Home Manager

Add the flake as an input and import its module in your Home Manager modules:

```nix
# In your flake inputs:
inputs.seep-reverse-lab.url = "github:angusdevgo/Seep-Reverse-Lab";
inputs.seep-reverse-lab.inputs.nixpkgs.follows = "nixpkgs";

# In a Home Manager configuration (with inputs passed through extraSpecialArgs):
{ inputs, ... }: {
  imports = [ inputs.seep-reverse-lab.homeManagerModules.default ];

  programs.seep-reverse-lab = {
    enable = true;
    optionalTools.androidTools = true;
    # optionalTools.frida = true;
    # optionalTools.ghidra = true;
  };
}
```

By default this installs the package, links all 10 skills into
`~/.pi/agent/skills`, and adds `seep` to Home Manager's shared
`programs.mcp.servers` registry (`~/.config/mcp/mcp.json`). Use a recent Home
Manager with `programs.mcp` support. Clients must be configured to consume that
registry; the module does not modify Pi's own MCP configuration or install the
Pi lab extension. DSH's plugin installation is described separately in
[INSTALL.md](../INSTALL.md#路线-bdeepseek-harness) and still requires a writable
checkout.

Available options under `programs.seep-reverse-lab`:

| Option | Default | Purpose |
| --- | --- | --- |
| `package` | This flake's package | Override the installed package and skill source |
| `installPackage` | `true` | Add the package to `home.packages` |
| `skills.enable` | `true` | Link the 10 skill directories |
| `skills.targetDirectory` | `".pi/agent/skills"` | Home-relative skill destination |
| `mcp.enable` | `true` | Register the server with `programs.mcp` |
| `optionalTools.androidTools` | `false` | Install ADB and Fastboot |
| `optionalTools.frida` | `false` | Install Frida host tools |
| `optionalTools.ghidra` | `false` | Install Ghidra |
| `optionalTools.androidSdk.enable` | `false` | Install Android SDK and export its location |
| `optionalTools.androidSdk.platformVersion` | `"35"` | Android platform version |
| `optionalTools.androidSdk.buildToolsVersion` | `"35.0.0"` | Android Build Tools version |

Android SDK users must explicitly configure license acceptance and unfree
packages in the **importing** nixpkgs configuration:

```nix
nixpkgs.config = {
  allowUnfree = true;
  android_sdk.accept_license = true;
};
programs.seep-reverse-lab.optionalTools.androidSdk.enable = true;
```

## Limits and verification

Optional integrations retain their own platform requirements: the web scripts
need PowerShell, Aotopsy is Windows-only, and IDA needs a separate licensed
installation. Node.js is provided, but the optional JS/browser MCP dependency
archives are not unpacked into the immutable package. The package does not run
the imperative setup or update scripts; update its flake input and rebuild your
Nix or Home Manager configuration instead.

```bash
nix build
nix flake check
```

The flake check starts both packaged entry points, verifies the MCP initialize
and tools/list exchange, checks all 10 skill entry files, and runs the packaged
JADX launcher and Apktool jar with `--version`. It does not invoke analysis tools. Builds and
checks currently target `x86_64-linux`. Linux ARM64 is not exposed because the
locked nixpkgs Apktool dependency `aapt` does not support that platform.

## 中文速览

NixOS 用户可用 `nix run` 启动 MCP，或通过 Home Manager 声明式安装包、10 个技能和
共享 MCP 注册表。无需向系统 Python 执行 pip 安装。Home Manager 的共享注册表不会
自动接入每个 Agent；Pi 需配置自己的 MCP 接线与 lab 扩展，DSH 插件仍按主安装文档使用
可写仓库。Android SDK、Frida、Ghidra 均按需开启；SDK 的许可证和非自由软件许可需在
调用方显式配置。更新时更新 flake 输入并重建配置。
