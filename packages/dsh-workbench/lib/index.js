/**
 * Seep 工作台 —— DeepSeek Harness 插件
 *
 * 这个包只做「接线」，不装工具。真正的工具（jadx / radare2 / apktool … 共 659 MB）
 * 在你 clone 的仓库里，本包靠配置里的路径指过去。
 *
 * 它负责三件事：
 *   1. 开机自检 —— 路径对不对、仓库全不全、版本够不够，缺什么直接说怎么补；
 *   2. 按配置挂载 —— 把 seep / js-reverse 两个 MCP 服务、技能目录在运行时挂上。
 *      路径改了不用改任何文件，DSH 重载这条 entry 就会用新路径重挂一遍；
 *   3. lab 开关 —— 每个会话默认关闭；只有消息里出现 `lab：` 才把作战纪律注进系统提示词。
 *
 * 配置项在 DSH 的「设置 → 插件」里能直接填（DSH 用 Config schema 自动生成表单）。
 */

import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';
import z from '@deepseek-ai/schemastery';
import * as McpClient from '@deepseek-ai/dsh-mcp-client';
import * as SkillFilesystem from '@deepseek-ai/dsh-skill-filesystem';
import * as ToolSkill from '@deepseek-ai/dsh-tool-skill';
import { installLabGate } from './lab-gate.js';

export const name = 'seep-workbench';

/** 需要系统提示词服务来注入作战纪律。 */
export const inject = ['systemPrompt'];

/**
 * 配置项声明。DSH 的设置界面会读这个 schema 自动生成表单，
 * 填完由 dsh-config-editor 写回当前 profile —— 用户改路径不用碰命令行，也不用改文件。
 */
export const Config = z.object({
  repoRoot: z
    .string()
    .default('')
    .description('工作台仓库路径（含 Tool 目录的那一层）。留空则读环境变量 SEEP_ROOT。'),
  pythonPath: z
    .string()
    .default('')
    .description('能 import mcp 的 python 解释器。留空则用 PATH 里的 python。'),
  enableSkills: z.boolean().default(true).description('在 DSH 里列出工作台的 10 个技能。'),
  labGate: z
    .boolean()
    .default(true)
    .description('只在消息里出现 lab： 之后才注入作战纪律。关掉便于排查问题。'),
});

/** 这个插件是按哪个仓库版本做的；仓库更旧就提醒用户先更新。 */
const MIN_REPO_VERSION = '1.14.0';

/** 必需的工具目录（缺了工具就跑不起来）。 */
const REQUIRED_DIRS = ['Tool/mcp', 'Tool/mcp/Tool/safe', 'Tool/skill'];

/** 作战纪律正文的仓库内位置（和 pi / Claude Code / Codex 共读同一个文件）。 */
const DISCIPLINE_FILE = 'Tool/prompts/SYSTEM.md';

/** 纯 stdio 服务，jadx 全量反编译、HLS 解密都要几分钟，不能用 DSH 的 60 秒默认值。 */
const SEEP_TIMEOUT_MS = 900000;
const JS_REVERSE_TIMEOUT_MS = 600000;

function readVersion(repoRoot) {
  try {
    return readFileSync(join(repoRoot, 'VERSION'), 'utf8').trim();
  } catch {
    return '';
  }
}

/** 版本号比较（只比点分数字，够用）。返回 true 表示 a 比 b 旧。 */
function isOlder(a, b) {
  const pa = String(a).split('.').map((n) => parseInt(n, 10) || 0);
  const pb = String(b).split('.').map((n) => parseInt(n, 10) || 0);
  for (let i = 0; i < Math.max(pa.length, pb.length); i += 1) {
    const x = pa[i] ?? 0;
    const y = pb[i] ?? 0;
    if (x !== y) return x < y;
  }
  return false;
}

/** 配置值优先；留空才退回环境变量。**两条路不会同时生效**，避免排查时分不清。 */
function resolveRoot(config = {}) {
  const fromConfig = String(config.repoRoot ?? '').trim();
  if (fromConfig) return fromConfig;
  return String(process.env.SEEP_ROOT ?? '').trim();
}

/** 把 %LOCALAPPDATA% / ~ 这类写法展开成真实路径。 */
function expand(p) {
  let out = String(p);
  out = out.replace(/%([A-Za-z_][A-Za-z0-9_]*)%/g, (m, k) => process.env[k] ?? m);
  if (out === '~' || out.startsWith('~/') || out.startsWith('~\\')) {
    out = join(homedir(), out.slice(1).replace(/^[/\\]/, ''));
  }
  return out;
}

/**
 * 找一个「能 import mcp」的 python。
 *
 * 顺序与 setup/tool-registry.json 里 python 那条的 chain 一致（env → candidates → path），
 * 不另外写一份硬编码清单 —— 用户改了 registry，插件跟着变。
 * 注意不能用 PATH 里的 `python` 当真：Windows 上它经常是商店占位别名，或者根本不存在。
 */
function resolvePython(config = {}) {
  const fromConfig = String(config.pythonPath ?? '').trim();
  if (fromConfig) return fromConfig;

  const fromEnv = String(process.env.SEEP_PYTHON ?? '').trim();
  if (fromEnv) return fromEnv;

  try {
    const registry = JSON.parse(
      readFileSync(join(resolveRoot(config), 'setup', 'tool-registry.json'), 'utf8'),
    );
    const list = Array.isArray(registry) ? registry : registry.tools ?? [];
    const entry = list.find((t) => t && t.id === 'python');
    for (const candidate of entry?.candidates ?? []) {
      const expanded = expand(candidate);
      if (existsSync(expanded)) return expanded;
    }
    for (const bundled of entry?.bundled ?? []) {
      const expanded = expand(bundled);
      if (existsSync(expanded)) return expanded;
    }
  } catch {
    // registry 读不到就退回 PATH，不让它阻止启动
  }

  return 'python';
}

/**
 * 开机自检。返回 { ok, lines, repoRoot, version }。
 * ok=false 表示「按现在的配置必然用不了」，此时不挂任何 MCP，但插件本身不抛异常。
 */
export function inspect(config = {}) {
  const lines = [];
  const repoRoot = resolveRoot(config);

  if (!repoRoot) {
    return {
      ok: false,
      repoRoot,
      version: '',
      lines: [
        '找不到工作台位置。两种填法，任选一种：',
        '  1) DSH 里打开 设置 → 插件 → seep-workbench-boot，把"工作台仓库路径"填上，保存即生效；',
        "  2) [Environment]::SetEnvironmentVariable('SEEP_ROOT', '<你 clone 的仓库路径>', 'User')",
      ],
    };
  }

  if (!existsSync(repoRoot)) {
    return {
      ok: false,
      repoRoot,
      version: '',
      lines: [
        `填的工作台路径不存在：${repoRoot}`,
        '确认路径写对了；如果还没下载工作台，先执行：',
        '  git clone https://github.com/angusdevgo/Seep-Reverse-Lab.git',
      ],
    };
  }

  const entry = join(repoRoot, 'Tool', 'mcp', 'seep_mcp_server.py');
  if (!existsSync(entry)) {
    return {
      ok: false,
      repoRoot,
      version: '',
      lines: [
        `这个目录不像工作台：缺少 ${entry}`,
        '路径要指到仓库根目录（里面能直接看到 Tool、MANUAL、setup 这几层）。',
      ],
    };
  }

  const missingDirs = REQUIRED_DIRS.filter((d) => !existsSync(join(repoRoot, d)));
  if (missingDirs.length > 0) {
    lines.push(`仓库不完整，缺少：${missingDirs.join(', ')}`);
    lines.push('这些目录里放的是工具本体，缺了工具会调用失败。建议重新 clone。');
  }

  const version = readVersion(repoRoot);
  if (version && isOlder(version, MIN_REPO_VERSION)) {
    lines.push(
      `仓库版本 ${version} 比插件要求的 ${MIN_REPO_VERSION} 旧，建议先在工作台目录执行 git pull。`,
    );
  }

  return { ok: missingDirs.length === 0, repoRoot, version, lines };
}

/** 挂载一个 MCP 服务。失败只记录，不影响其它服务，也不让整条 profile 起不来。 */
function mountMcp(ctx, spec, mounted, lines) {
  try {
    ctx.plugin(McpClient, {
      serverName: spec.serverName,
      transport: 'stdio',
      command: spec.command,
      args: spec.args,
      cwd: spec.cwd,
      env: { PYTHONIOENCODING: 'utf-8' },
      toolCallTimeoutMs: spec.timeoutMs,
      failOnStartupError: false,
    });
    mounted[spec.key] = true;
  } catch (error) {
    mounted[spec.key] = false;
    lines.push(`挂载 ${spec.serverName} 失败：${error instanceof Error ? error.message : String(error)}`);
  }
}

/** 状态文件：给校验脚本读，省得去猜运行时到底挂上了什么。 */
function statusPath() {
  const home = String(process.env.DSH_HOME ?? '').trim() || join(homedir(), '.dsh');
  return join(home, 'seep-workbench.status.json');
}

function writeStatus(payload) {
  // 测试钩子：SEEP_WORKBENCH_EVIDENCE 指向任意文件时，额外写一份到那里。
  const targets = [statusPath()];
  const evidence = String(process.env.SEEP_WORKBENCH_EVIDENCE ?? '').trim();
  if (evidence) targets.push(evidence);

  for (const target of targets) {
    try {
      mkdirSync(join(target, '..'), { recursive: true });
      writeFileSync(target, `${JSON.stringify(payload)}\n`, 'utf8');
    } catch {
      // 写不进状态文件不影响正常使用
    }
  }
}

export function apply(ctx, config = {}) {
  const result = inspect(config);
  const repoRoot = result.repoRoot;
  const mounted = { seep: false, jsReverse: false, skills: false };
  const lines = [...result.lines];

  if (result.ok) {
    const python = resolvePython(config);

    mountMcp(
      ctx,
      {
        key: 'seep',
        serverName: 'seep',
        command: python,
        args: [join(repoRoot, 'Tool', 'mcp', 'seep_mcp_server.py')],
        cwd: repoRoot,
        timeoutMs: SEEP_TIMEOUT_MS,
      },
      mounted,
      lines,
    );

    mountMcp(
      ctx,
      {
        key: 'jsReverse',
        serverName: 'js-reverse',
        command: 'npx',
        args: ['-y', 'js-reverse-mcp'],
        cwd: repoRoot,
        timeoutMs: JS_REVERSE_TIMEOUT_MS,
      },
      mounted,
      lines,
    );

    if (config.enableSkills !== false) {
      try {
        ctx.plugin(SkillFilesystem, {
          customSkillDirs: [
            join(repoRoot, 'Tool', 'skill'),
            join(repoRoot, 'Tool', 'skill', 'safe-skills'),
          ],
        });
        ctx.plugin(ToolSkill, {});
        mounted.skills = true;
      } catch (error) {
        lines.push(
          `挂载技能失败：${error instanceof Error ? error.message : String(error)}`,
        );
      }
    }
  }

  // 纪律正文只在 lab 开关打开时才需要。读一次缓存住，文件没了就降级。
  let discipline = '';
  const labGate = config.labGate !== false;
  if (labGate) {
    const file = join(repoRoot || '', DISCIPLINE_FILE);
    if (repoRoot && existsSync(file)) {
      try {
        discipline = readFileSync(file, 'utf8');
      } catch {
        discipline = '';
      }
    }
    if (result.ok && !discipline) {
      lines.push(`${DISCIPLINE_FILE} 没读到，lab 开关降级为「只切换状态、不注入正文」。`);
    }
    installLabGate(ctx, { discipline });
  }

  const ok = result.ok && mounted.seep;
  if (ok) {
    const wired = [
      mounted.seep ? 'seep' : '',
      mounted.jsReverse ? 'js-reverse' : '',
      mounted.skills ? '技能' : '',
    ].filter(Boolean);
    console.error(
      `[seep-workbench] 就绪：工作台 ${repoRoot}（版本 ${result.version || '未知'}），已接线 ${wired.join(' / ')}` +
        (labGate ? '，lab 开关已启用' : '，lab 开关已关闭'),
    );
    for (const line of lines) console.error(`[seep-workbench]   提示：${line}`);
  } else {
    // 用 console.error 而非抛异常：插件抛错可能整条 profile 都起不来，
    // 但这种问题往往只是「路径没填 / 工具没下载好」，不该连带影响普通对话。
    console.error('[seep-workbench] 自检没通过：');
    for (const line of lines) console.error(`[seep-workbench]   ${line}`);
    if (config.strict === true) {
      throw new Error('seep-workbench: 自检失败（strict 模式）');
    }
  }

  writeStatus({
    at: new Date().toISOString(),
    ok,
    repoRoot,
    version: result.version,
    python: result.ok ? resolvePython(config) : '',
    mounted,
    skillsEnabled: config.enableSkills !== false,
    labGate,
    lines,
  });

  return { ...result, ok, mounted, lines };
}
