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

import { spawnSync } from 'node:child_process';
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
    .volatile()
    .description('工作台仓库路径（含 Tool 目录的那一层）。留空则读环境变量 SEEP_ROOT。'),
  pythonPath: z
    .string()
    .default('')
    .volatile()
    .description('能 import mcp 的 python 解释器。留空则用 PATH 里的 python。'),
  enableSkills: z.boolean().default(true).volatile().description('在 DSH 里列出工作台的 10 个技能。'),
  labGate: z
    .boolean()
    .default(true)
    .volatile()
    .description('只在消息里出现 lab： 之后才注入作战纪律。关掉便于排查问题。'),
});

/**
 * 把配置读成普通值。
 *
 * DSH 的 volatile 字段在宿主里是引用（config.x.get()），不是裸值；
 * 我们内部统一按普通值处理，所以入口处解一次。
 * 为什么要 volatile：DSH 只把 volatile 字段投影到设置表单里，
 * 普通字段根本不进表单 —— 那样面板就看不到也改不了。
 */
function readConfig(config = {}) {
  const plain = (ref, fallback) => {
    if (ref === undefined) return fallback;
    if (ref !== null && typeof ref === 'object' && typeof ref.get === 'function') {
      const value = ref.get();
      return value === undefined ? fallback : value;
    }
    return ref;
  };
  return {
    repoRoot: plain(config.repoRoot, ''),
    pythonPath: plain(config.pythonPath, ''),
    enableSkills: plain(config.enableSkills, true) !== false,
    labGate: plain(config.labGate, true) !== false,
    strict: config.strict === true,
  };
}

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

// ---------------------------------------------------------------- 工具扫描
// 面板要显示「哪个工具找到、哪个缺」。浏览器读不到磁盘，所以由宿主算好给它。

/** PATH 里按名字找可执行文件（Windows 要补 .exe/.cmd/.bat）。 */
function whichInPath(names) {
  const dirs = String(process.env.PATH ?? '').split(process.platform === 'win32' ? ';' : ':');
  const exts = process.platform === 'win32' ? ['', '.exe', '.cmd', '.bat'] : [''];
  for (const name of names ?? []) {
    for (const dir of dirs) {
      if (!dir) continue;
      for (const ext of exts) {
        const candidate = join(dir, name + ext);
        if (existsSync(candidate)) return candidate;
      }
    }
  }
  return '';
}

/**
 * 快速扫一遍工具在哪。只做「找得到吗」，不真启动 —— 真启动是面板上「深度检测」按钮的事。
 * 状态用 tool_resolver.py 的同一套词汇，免得两处说法不一致。
 */
function scanTools(repoRoot) {
  let registry = [];
  try {
    const raw = JSON.parse(readFileSync(join(repoRoot, 'setup', 'tool-registry.json'), 'utf8'));
    registry = Array.isArray(raw) ? raw : raw.tools ?? [];
  } catch {
    return {};
  }

  const out = {};
  for (const tool of registry) {
    const id = tool?.id;
    if (!id) continue;
    const envName = tool.env ? String(process.env[tool.env] ?? '').trim() : '';
    let path = '';
    let source = '';

    if (envName && existsSync(envName)) {
      path = envName;
      source = 'env';
    }
    if (!path) {
      for (const candidate of tool.candidates ?? []) {
        const expanded = expand(candidate);
        // 候选里可能写的是目录（比如安装根），存在就算找到
        if (expanded && existsSync(expanded)) {
          path = expanded;
          source = 'candidates';
          break;
        }
      }
    }
    if (!path) {
      for (const bundled of tool.bundled ?? []) {
        const expanded = expand(bundled);
        if (expanded && existsSync(expanded)) {
          path = expanded;
          source = 'bundled';
          break;
        }
      }
    }
    if (!path) {
      const found = whichInPath(tool.path_names);
      if (found) {
        path = found;
        source = 'path';
      }
    }

    const optional = tool.kind === 'optional';
    out[id] = {
      state: path ? 'READY' : optional ? 'OPTIONAL' : 'MISSING',
      source,
      path,
      detail: path ? `找到：${source}` : optional ? '未安装（不影响使用）' : '找不到，需要安装',
      fix: path ? '' : tool.fix || '',
    };
  }
  return out;
}

/**
 * 深度检测：真启动每个工具验一下（慢，几秒到几十秒）。
 * 结果与 `python Tool/mcp/tool_resolver.py --verify --json` 完全一致 —— 就是调它。
 */
function probeTools(repoRoot, python) {
  try {
    const result = spawnSync(
      python,
      [join(repoRoot, 'Tool', 'mcp', 'tool_resolver.py'), '--verify', '--json'],
      { cwd: repoRoot, encoding: 'utf8', timeout: 180000, windowsHide: true },
    );
    const text = String(result.stdout ?? '');
    const start = text.indexOf('{');
    if (start >= 0) {
      const parsed = JSON.parse(text.slice(start));
      return parsed.tools ?? {};
    }
  } catch {
    // 深度检测失败不该让面板整页报错，退回快速扫描即可
  }
  return scanTools(repoRoot);
}

/** 工具扫描很贵，缓存 60 秒；深度检测缓存 5 分钟。 */
const toolCache = new Map();

function toolsFor(repoRoot, python, deep) {
  const key = `${repoRoot}|${deep ? 'deep' : 'fast'}`;
  const ttl = deep ? 300000 : 60000;
  const hit = toolCache.get(key);
  if (hit && Date.now() - hit.at < ttl) return hit.value;
  const value = deep ? probeTools(repoRoot, python) : scanTools(repoRoot);
  toolCache.set(key, { at: Date.now(), value });
  return value;
}

// ---------------------------------------------------------------- 面板接口
// 只读接口，给浏览器面板用。浏览器读不到磁盘，工具在不在只有宿主知道。

const API_PATH = '/seep-workbench/api';

/** 只放本机回环访问，避免把本机路径暴露给别的机器。 */
function allowedPeer(req) {
  const host = String(req.headers.host ?? '');
  const hostLocal = /^(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$/i.test(host);
  const remote = String(req.socket?.remoteAddress ?? '');
  const loopback = remote === '127.0.0.1' || remote === '::1' || remote === '::ffff:127.0.0.1';
  if (!loopback && !hostLocal) return false;
  const origin = req.headers.origin;
  if (origin === undefined || origin === '' || origin === 'null') return true;
  try {
    return new URL(origin).host === host;
  } catch {
    return false;
  }
}

function sendJson(res, code, payload) {
  const body = JSON.stringify(payload);
  res.writeHead(code, {
    'content-type': 'application/json; charset=utf-8',
    'cache-control': 'no-store',
    'content-length': Buffer.byteLength(body),
  });
  res.end(body);
}

/**
 * 注册 /seep-workbench/api。web profile 才有 webServer，其它 profile 静默跳过。
 * 用 ctx.inject 声明依赖，这样服务晚到也能挂上，服务没有就整个跳过。
 */
function registerPanelApi(ctx, config) {
  ctx.inject(['webServer'], (scope) => {
    scope.webServer.register({
      kind: 'exact',
      path: API_PATH,
      handler: (req, res) => {
        if (!allowedPeer(req)) {
          sendJson(res, 403, { ok: false, error: 'only loopback' });
          return;
        }
        if (req.method !== 'GET' && req.method !== 'HEAD') {
          sendJson(res, 405, { ok: false, error: 'GET only' });
          return;
        }
        const deep = /[?&]verify=1/.test(String(req.url ?? ''));
        const live = readConfig(config);
        const result = inspect(live);
        const repoRoot = result.repoRoot;
        const python = resolvePython(live);
        const mountedNow = result.ok && existsSync(join(repoRoot, 'Tool', 'mcp', 'seep_mcp_server.py'));
        const wired = mountedNow ? 'seep / js-reverse / 技能' : '无';

        sendJson(res, 200, {
          ok: Boolean(mountedNow),
          repoRoot,
          version: result.version,
          python,
          wired,
          labGate: live.labGate,
          skillsEnabled: live.enableSkills,
          deep,
          lines: result.lines,
          tools: result.ok ? toolsFor(repoRoot, python, deep) : {},
        });
      },
    });
  });
}

export function apply(ctx, rawConfig = {}) {
  const config = readConfig(rawConfig);
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
    if (config.strict) {
      throw new Error('seep-workbench: 自检失败（strict 模式）');
    }
  }

  // 面板里改了配置，宿主会发这个事件。现在已经挂着的 MCP 不会自己换路径，
  // 所以这里只把新值读进来（面板立刻显示新路径）并明确提示要重启。
  if (typeof ctx?.on === 'function') {
    ctx.on('loader/volatile-update', () => {
      const now = readConfig(rawConfig);
      const changed = now.repoRoot !== config.repoRoot || now.pythonPath !== config.pythonPath;
      console.error(
        changed
          ? `[seep-workbench] 配置已更新为 ${now.repoRoot}，重启 DSH 后新路径才会真正生效`
          : '[seep-workbench] 配置已更新（技能 / lab 开关对下一个会话生效）',
      );
    });
  }

  if (typeof ctx?.inject === 'function') {
    try {
      registerPanelApi(ctx, rawConfig);
    } catch (error) {
      lines.push(`面板接口没挂上：${error instanceof Error ? error.message : String(error)}`);
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
