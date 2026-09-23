import idaapi
import ida_auto
print("[*] Script executed in IDA Pro!")
idaapi.load_and_run_plugin("ida_mcp", 1)
print("[*] MCP plugin run called!")
