"""Check the installed package and MCP transport without invoking analysis tools."""

import asyncio
import os
from pathlib import Path
import subprocess
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def check_server(command):
    params = StdioServerParameters(command=str(command), env=dict(os.environ))
    async with stdio_client(params) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            result = await session.initialize()
            assert result.model_dump(by_alias=True)["serverInfo"]["name"], "Missing MCP server identity"
            tools = await session.list_tools()
            assert tools.tools, "The installed MCP server exposes no tools"
            print(f"{command.name}: MCP handshake and {len(tools.tools)} tool definitions OK")


async def main():
    package = Path(sys.argv[1])
    root = package / "share/seep-reverse-lab"
    safe = root / "Tool/mcp/Tool/safe"
    for name in ("apkseep", "client-license-validation-bypass", "exe-reverse", "softseep", "webseep"):
        assert (root / "Tool/skill" / name / "SKILL.md").is_file(), name
    for name in ("apk-reverse", "ida-reverse", "mcp-js-reverse-playbook", "radare2", "reverse-engineering"):
        assert (root / "Tool/skill/safe-skills" / name / "SKILL.md").is_file(), name
    jadx = safe / "jadx/bin/jadx"
    apktool = safe / "apktool/apktool.jar"
    assert jadx.is_symlink() and jadx.is_file(), "Missing native JADX launcher"
    assert apktool.is_symlink() and apktool.is_file(), "Missing Nix Apktool jar"
    subprocess.run([str(jadx), "--version"], check=True, timeout=60)
    subprocess.run(["java", "-jar", str(apktool), "--version"], check=True, timeout=60)
    for name in ("seep-reverse-lab", "seep-mcp"):
        await asyncio.wait_for(check_server(package / "bin" / name), timeout=60)


asyncio.run(main())
