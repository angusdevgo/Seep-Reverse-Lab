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

import { execFileSync, spawn, spawnSync } from 'node:child_process';
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
  contentRoot: z
    .string()
    .default('')
    .volatile()
    .description('内容层目录（技能/知识库/案例）。留空则用仓库里的 Tool/skill 等。'),
  contentRepo: z
    .string()
    .default('')
    .volatile()
    .description('内容层的 git 地址。填了之后面板上的「更新内容」会去拉它。'),
  enableIda: z
    .boolean()
    .default(false)
    .volatile()
    .description('额外挂 IDA Pro MCP（需要本机已装 IDA + ida_pro_mcp）。'),
  enablePlaywright: z
    .boolean()
    .default(false)
    .volatile()
    .description('额外挂 Playwright MCP（浏览器自动化，走 npx）。'),
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
    contentRoot: plain(config.contentRoot, ''),
    contentRepo: plain(config.contentRepo, ''),
    enableIda: plain(config.enableIda, false) === true,
    enablePlaywright: plain(config.enablePlaywright, false) === true,
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
const PLAYWRIGHT_TIMEOUT_MS = 600000;
const IDA_TIMEOUT_MS = 600000;

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
 * 内容层目录：技能 / 知识库 / 案例。
 *
 * 顺序：配置里的 contentRoot → 环境变量 SEEP_CONTENT_ROOT → 空（用仓库自带的那份）。
 * 约定布局：<root>/skill、<root>/safe-skills、<root>/kb、<root>/cases。
 */
function resolveContentRoot(config = {}) {
  const fromConfig = String(config.contentRoot ?? '').trim();
  if (fromConfig) return expand(fromConfig);
  const fromEnv = String(process.env.SEEP_CONTENT_ROOT ?? '').trim();
  return fromEnv ? expand(fromEnv) : '';
}

/** 读内容根的 git 状态（用于面板显示「更到哪一版了」）。 */
function contentStatus(root) {
  if (!root) return null;
  if (!existsSync(join(root, '.git'))) return { inside: false, commit: '', date: '' };
  try {
    const commit = execFileSync('git', ['-C', root, 'rev-parse', '--short', 'HEAD'], {
      encoding: 'utf8',
      timeout: 10000,
    }).trim();
    const date = execFileSync('git', ['-C', root, 'log', '-1', '--format=%cI'], {
      encoding: 'utf8',
      timeout: 10000,
    }).trim();
    return { inside: true, commit, date };
  } catch {
    return { inside: true, commit: '', date: '' };
  }
}

/**
 * 找 IDA 的 MCP 服务端。IDA 自带的 python311 里装了 ida_pro_mcp 才能用。
 *
 * 顺序：SEEP_IDA_ROOT 环境变量 → setup/tool-registry.json 的 ida 候选目录。
 * 返回 { python, server } 或 null（null 表示这台机器上没有可用的 IDA，不是错误）。
 */
function resolveIda(config = {}) {
  const roots = [];
  const fromEnv = String(process.env.SEEP_IDA_ROOT ?? '').trim();
  if (fromEnv) roots.push(fromEnv);

  try {
    const registry = JSON.parse(
      readFileSync(join(resolveRoot(config), 'setup', 'tool-registry.json'), 'utf8'),
    );
    const list = Array.isArray(registry) ? registry : registry.tools ?? [];
    const entry = list.find((t) => t && t.id === 'ida');
    for (const candidate of entry?.candidates ?? []) roots.push(expand(candidate));
  } catch {
    // 读不到注册表就只认环境变量
  }

  for (const root of roots) {
    if (!root || !existsSync(root)) continue;
    const python = join(root, 'python311', process.platform === 'win32' ? 'python.exe' : 'bin/python3');
    const server = join(root, 'python311', 'Lib', 'site-packages', 'ida_pro_mcp', 'server.py');
    if (existsSync(python) && existsSync(server)) return { python, server };
  }
  return null;
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
      env: { PYTHONIOENCODING: 'utf-8', ...(spec.env || {}) },
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

// ---------------------------------------------------------------- 技能注册表探测
// 只写 mounted.skills: true 说明不了技能真的注册上了 —— 那只是「调了 ctx.plugin」。
// 这里等 provider 就绪后问一次真实的注册表：到底能列出几个技能、叫什么。
// 探测失败不影响使用，状态文件里保持 skills: null 即可。
function probeSkills(ctx, repoRoot, delayMs = 1200) {
  return new Promise((resolve) => {
    let settled = false;
    const finish = (value) => {
      if (settled) return;
      settled = true;
      resolve(value);
    };

    // 注册表是服务，不能在没 inject 的上下文里直接读（cordis 会抛
    // "cannot get property ... without inject"），只能走 inject 回调。
    // 回调不保证同步触发，所以要等它，并留一个兜底超时。
    setTimeout(() => {
      try {
        ctx.inject(['skills'], (scope) => {
          void (async () => {
            try {
              const shot = await scope.skills.snapshot({ cwd: repoRoot });
              const list = Array.isArray(shot?.skills) ? shot.skills : Array.isArray(shot) ? shot : [];
              finish({
                count: list.length,
                complete: shot?.complete !== false,
                names: list.map((entry) => String(entry?.name ?? '')).filter(Boolean).sort(),
              });
            } catch (error) {
              console.error(
                `[seep-workbench] 技能探测失败：${error instanceof Error ? error.message : String(error)}`,
              );
              finish(null);
            }
          })();
        });
      } catch (error) {
        console.error(
          `[seep-workbench] 技能探测注入失败：${error instanceof Error ? error.message : String(error)}`,
        );
        finish(null);
      }
      setTimeout(() => {
        if (!settled) {
          console.error('[seep-workbench] 技能探测超时：skills 服务没就绪');
          finish(null);
        }
      }, 6000);
    }, delayMs);
  });
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
 * 读 setup/tool-paths.local.json（面板里给某个工具手填的路径）。
 * 文件不存在时返回空对象 —— 绝大多数人不会用它。
 */
function readUserPaths(repoRoot) {
  try {
    const raw = JSON.parse(readFileSync(join(repoRoot, 'setup', 'tool-paths.local.json'), 'utf8'));
    const tools = raw?.tools;
    return tools && typeof tools === 'object' ? tools : {};
  } catch {
    return {};
  }
}

/**
 * 写入/清除某个工具的人工路径。
 *
 * 只接受「存在」的路径，写之前先把目录/文件判一遍，免得面板里点了保存却存了个错路径。
 * 返回 { ok, tools, error }。
 */
function writeUserPath(repoRoot, toolId, value) {
  const id = String(toolId ?? '').trim();
  if (!id) return { ok: false, error: '缺少工具 id' };
  const file = join(repoRoot, 'setup', 'tool-paths.local.json');
  const current = readUserPaths(repoRoot);
  const raw = String(value ?? '').trim();

  if (raw) {
    const expanded = expand(raw);
    if (!existsSync(expanded)) return { ok: false, error: `路径不存在：${expanded}` };
    current[id] = raw;
  } else {
    delete current[id];
  }

  try {
    mkdirSync(join(file, '..'), { recursive: true });
    writeFileSync(
      file,
      `${JSON.stringify({ _comment: '人工指定的工具路径（面板或命令写入，留空即恢复自动查找）。本文件不进 git。', tools: current }, null, 2)}
`,
      'utf8',
    );
  } catch (error) {
    return { ok: false, error: `写入失败：${error instanceof Error ? error.message : String(error)}` };
  }
  return { ok: true, tools: current };
}

/**
 * 读一个 git 目录的状态：分支、落后/领先多少、工作区脏不脏、差哪些提交。
 *
 * 「对比现有文件和仓库文件」就靠它 —— 先 fetch 再看，不改任何文件。
 * 失败一律返回 error，不让面板崩。
 */
function gitStatus(root, { fetch = false } = {}) {
  if (!root || !existsSync(root)) return { ok: false, error: '目录不存在' };
  if (!existsSync(join(root, '.git'))) return { ok: false, error: '不是 git 仓库' };

  const run = (args) =>
    execFileSync('git', ['-C', root, ...args], { encoding: 'utf8', timeout: 30000 }).trim();
  const lines = (text) => String(text).split(/\r?\n/).filter(Boolean);

  try {
    if (fetch) {
      try {
        execFileSync('git', ['-C', root, 'fetch', '--quiet'], { encoding: 'utf8', timeout: 60000 });
      } catch {
        // 没网 / 没凭据都不能挡住读本地状态
      }
    }

    const branch = run(['rev-parse', '--abbrev-ref', 'HEAD']);
    const commit = run(['rev-parse', '--short', 'HEAD']);
    const date = run(['log', '-1', '--format=%cI']);
    const dirty = lines(run(['status', '--porcelain'])).length;

    let upstream = '';
    let behind = 0;
    let ahead = 0;
    let commits = [];
    try {
      upstream = run(['rev-parse', '--abbrev-ref', '--symbolic-full-name', '@{u}']);
      behind = Number(run(['rev-list', '--count', 'HEAD..@{u}'])) || 0;
      ahead = Number(run(['rev-list', '--count', '@{u}..HEAD'])) || 0;
      if (behind > 0) commits = lines(run(['log', '--oneline', '--no-decorate', 'HEAD..@{u}', '-10']));
    } catch {
      // 还没关联远端分支，就只报本地状态
    }

    return { ok: true, branch, commit, date, dirty, upstream, behind, ahead, commits };
  } catch (error) {
    const text = error instanceof Error ? error.message : String(error);
    return { ok: false, error: text.split(/\r?\n/)[0] };
  }
}

/**
 * 对任意 git 目录「先看再拉」：fetch → 报告落后多少 → pull --ff-only。
 *
 * 只快进，不合并、不 rebase、不丢本地改动 —— 更新失败比更新出错好。
 */
function updateGitDir(root, label) {
  if (!root) return { ok: false, message: `${label}还没配路径` };
  const before = gitStatus(root);
  if (!before.ok) return { ok: false, message: `${label}不是可用的 git 仓库：${before.error}` };

  let pulled = '';
  try {
    pulled = execFileSync('git', ['-C', root, 'pull', '--ff-only', '--no-rebase'], {
      encoding: 'utf8',
      timeout: 180000,
    });
  } catch (error) {
    const text = error instanceof Error ? error.message : String(error);
    return {
      ok: false,
      message: `${label}更新失败：${text.split(/\r?\n/)[0]}`,
      detail: text.slice(0, 400),
      before,
    };
  }

  const after = gitStatus(root);
  const changed = before.commit !== after.commit;
  return {
    ok: true,
    changed,
    before: before.commit,
    after: after.commit,
    pending: before.behind,
    message: changed
      ? `${label}已更新：${before.commit} → ${after.commit}${before.behind ? `（${before.behind} 个提交）` : ''}`
      : `${label}已经是最新（${after.commit}）`,
    detail: String(pulled).trim().split(/\r?\n/).slice(-2).join(' / '),
  };
}

/**
 * 更新内容层。
 *
 * 只做一件确定的事：内容根是 git 仓库就 `git pull --ff-only`；不是就返回原因，
 * 不去猜、不去下载压缩包 —— 猜错的更新比不更新更糟。
 *
 * 返回 { ok, before, after, changed, files, message }。
 */
function updateContent(config = {}) {
  const root = resolveContentRoot(config);
  if (!root) {
    return { ok: false, message: '还没配内容目录。填一个内容仓库的本地路径，或直接留空用仓库自带的。' };
  }
  if (!existsSync(root)) {
    return { ok: false, message: `内容目录不存在：${root}` };
  }
  if (!existsSync(join(root, '.git'))) {
    return {
      ok: false,
      message: `${root} 不是 git 仓库，没法自动更新（可以手动覆盖文件，或把它改成 git clone 出来的目录）。`,
    };
  }

  const head = (args) =>
    execFileSync('git', ['-C', root, ...args], { encoding: 'utf8', timeout: 20000 }).trim();

  let before = '';
  try {
    before = head(['rev-parse', 'HEAD']);
  } catch {
    /* 空仓库 */
  }

  try {
    const out = execFileSync('git', ['-C', root, 'pull', '--ff-only', '--no-rebase'], {
      encoding: 'utf8',
      timeout: 120000,
    });
    const after = head(['rev-parse', 'HEAD']);
    const changed = Boolean(before) && before !== after;
    let files = 0;
    if (changed) {
      try {
        files = Number(head(['rev-list', '--count', `${before}..${after}`])) || 0;
      } catch {
        files = 0;
      }
    }
    return {
      ok: true,
      before: before.slice(0, 7),
      after: after.slice(0, 7),
      changed,
      commits: files,
      message: changed ? `已更新到 ${after.slice(0, 7)}（${files} 个提交）` : '已经是最新',
      output: String(out).trim().split(/\r?\n/).slice(-3).join(' / '),
    };
  } catch (error) {
    const text = error instanceof Error ? error.message : String(error);
    const firstLine = text.split(/\r?\n/)[0];
    return { ok: false, message: `git pull 失败：${firstLine}`, output: text.slice(0, 400) };
  }
}

/**
 * 快速扫一遍工具在哪。只做「找得到吗」，不真启动 —— 真启动是面板上「深度检测」按钮的事。
 * 状态用 tool_resolver.py 的同一套词汇，免得两处说法不一致。
 */
/**
 * 这个插件是怎么装进来的。
 *
 *   file: / link:  → 开发者模式（硬链接或本地 tgz），改代码即生效，没有「更新」概念
 *   版本号/范围     → 从 npm 装的，`dsh plugin update` 才有意义
 */
/** 插件自己的版本号（读包内的 package.json）。读不到就返回空串，不抛。 */
function selfVersion() {
  try {
    const self = join(import.meta.dirname ?? '', '..', 'package.json');
    return JSON.parse(readFileSync(self, 'utf8')).version || '';
  } catch {
    return '';
  }
}

function pluginInstallInfo() {
  const home = String(process.env.DSH_HOME ?? '').trim() || join(homedir(), '.dsh');
  const profile = String(process.env.SEEP_DSH_PROFILE ?? '').trim() || 'web';
  const pkgFile = join(home, 'profiles', profile, 'package.json');

  let spec = '';
  try {
    const data = JSON.parse(readFileSync(pkgFile, 'utf8'));
    spec = String((data.dependencies || {})['seep-dsh-workbench'] ?? '');
  } catch {
    spec = '';
  }

  const local = spec.startsWith('file:') || spec.startsWith('link:');
  return {
    spec,
    local,
    profile,
    mode: local
      ? spec.endsWith('.tgz')
        ? 'tgz 本地包（不会自动更新，换新版要重新 add）'
        : '开发者模式（本地目录硬链接，改代码即生效）'
      : spec
        ? 'npm（可以自动更新）'
        : '未知来源',
    updatable: Boolean(spec) && !local,
    version: selfVersion(),
  };
}

/**
 * 从 npm 更新插件。
 *
 * 只对 npm 来源有效 —— 本地文件/目录安装没有远端可拉，直说，不去猜。
 * 更新完必须重启 DSH：插件代码是启动时加载的。
 */
function updatePlugin() {
  const info = pluginInstallInfo();
  if (!info.updatable) {
    return {
      ok: false,
      message: `当前是${info.mode}，没有可拉取的远端。要自动更新请改成 npm 安装：dsh plugin --profile ${info.profile} add seep-dsh-workbench`,
      install: info,
    };
  }

  try {
    const out = execFileSync(
      process.platform === 'win32' ? 'dsh.cmd' : 'dsh',
      ['plugin', '--profile', info.profile, 'add', 'seep-dsh-workbench@latest'],
      { encoding: 'utf8', timeout: 180000, shell: process.platform === 'win32' },
    );
    return {
      ok: true,
      message: '插件已更新到最新版，重启 DSH 生效',
      detail: String(out).trim().split(/\r?\n/).slice(-2).join(' / '),
      install: pluginInstallInfo(),
    };
  } catch (error) {
    const text = error instanceof Error ? error.message : String(error);
    return {
      ok: false,
      message: `更新失败：${text.split(/\r?\n/)[0]}`,
      detail: text.slice(0, 400),
      install: info,
    };
  }
}

/**
 * 面板里点「重启 DSH」走这里。
 *
 * 为什么需要一个「帮手进程」而不是自己重启自己：
 *   node 进程没法原地重启，必须有人等它死了再把新的拉起来。
 *   所以我们 spawn 一个脱离父进程的小脚本，它轮询老 PID 是否消失，
 *   老进程一退出就按**完全相同的命令行**把 DSH 重新拉起来。
 *
 * 命令行从 process.argv 原样复制（含 --profile web 之类的参数），
 * 这样用户当初怎么启动的，重启后还是怎么启动。
 *
 * 失败不静默：日志写到 ~/.dsh/seep-workbench.restart.log，面板上也会回一条
 * 「没起来就手动敲 xxx」。
 */
function scheduleRestart(delayMs = 800) {
  const argv = process.argv.slice(1);
  const pid = process.pid;
  const home = String(process.env.DSH_HOME ?? '').trim() || join(homedir(), '.dsh');
  const logFile = join(home, 'seep-workbench.restart.log');

  // 帮手脚本：等老进程退出 → 等一下让端口释放 → 原样拉起
  const helper = `
const { spawn } = require('node:child_process');
const fs = require('node:fs');
const argv = JSON.parse(process.env.SEEP_RESTART_ARGV);
const oldPid = Number(process.env.SEEP_RESTART_PID);
const logFile = process.env.SEEP_RESTART_LOG;
const note = (m) => { try { fs.appendFileSync(logFile, new Date().toISOString() + ' ' + m + '\n'); } catch {} };
const alive = () => { try { process.kill(oldPid, 0); return true; } catch { return false; } };
const t0 = Date.now();
const wait = () => {
  if (alive() && Date.now() - t0 < 20000) return setTimeout(wait, 250);
  note('old process gone, starting new dsh');
  setTimeout(() => {
    try {
      const child = spawn(process.execPath, argv, { detached: true, stdio: 'ignore', env: process.env, cwd: process.cwd() });
      child.unref();
      note('spawned pid ' + child.pid);
    } catch (e) { note('spawn failed: ' + e.message); }
    process.exit(0);
  }, ${delayMs});
};
note('waiting for pid ' + oldPid);
wait();
`;

  try {
    writeFileSync(logFile, '');
  } catch {
    /* 日志写不了不影响重启 */
  }

  try {
    const child = spawn(process.execPath, ['-e', helper], {
      detached: true,
      stdio: 'ignore',
      cwd: process.cwd(),
      env: {
        ...process.env,
        SEEP_RESTART_ARGV: JSON.stringify(argv),
        SEEP_RESTART_PID: String(pid),
        SEEP_RESTART_LOG: logFile,
      },
    });
    child.unref();
  } catch (error) {
    const text = error instanceof Error ? error.message : String(error);
    return {
      ok: false,
      message: `重启帮手没起来：${text.split(/\r?\n/)[0]}。请手动重启：dsh ${argv.slice(1).join(' ')}`,
    };
  }

  return {
    ok: true,
    message: '正在重启 DSH，页面会在十几秒后自动回来（如果没回来，手动敲 dsh 重启）',
    command: `dsh ${argv.slice(1).join(' ')}`,
    log: logFile,
  };
}

function scanTools(repoRoot) {
  let registry = [];
  try {
    const raw = JSON.parse(readFileSync(join(repoRoot, 'setup', 'tool-registry.json'), 'utf8'));
    registry = Array.isArray(raw) ? raw : raw.tools ?? [];
  } catch {
    return {};
  }

  const out = {};
  const userPaths = readUserPaths(repoRoot);
  for (const tool of registry) {
    const id = tool?.id;
    if (!id) continue;
    const envName = tool.env ? String(process.env[tool.env] ?? '').trim() : '';
    let path = '';
    let source = '';

    const manual = String(userPaths[id] ?? '').trim();
    if (manual) {
      const expandedManual = expand(manual);
      if (existsSync(expandedManual)) {
        path = expandedManual;
        source = 'user';
      }
    }
    if (!path && envName && existsSync(envName)) {
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
function registerPanelApi(ctx, config, getLab) {
  ctx.inject(['webServer'], (scope) => {
    scope.webServer.register({
      kind: 'exact',
      path: API_PATH,
      handler: (req, res) => {
        try {
        if (!allowedPeer(req)) {
          sendJson(res, 403, { ok: false, error: 'only loopback' });
          return;
        }
        // POST：面板里给某个工具手填路径。只接受本机回环，写的是仓库内的覆盖文件。
        if (req.method === 'POST') {
          try {
          const chunks = [];
          let size = 0;
          req.on('data', (chunk) => {
            size += chunk.length;
            if (size > 8192) {
              req.destroy();
              return;
            }
            chunks.push(chunk);
          });
          req.on('end', () => {
            let payload = {};
            try {
              payload = JSON.parse(Buffer.concat(chunks).toString('utf8') || '{}');
            } catch {
              sendJson(res, 400, { ok: false, error: '请求体不是合法 JSON' });
              return;
            }
            const liveConfig = readConfig(config);
            const root = resolveRoot(liveConfig);
            const check = inspect(liveConfig);
            if (!check.ok) {
              sendJson(res, 400, { ok: false, error: '工作台路径还没配好，先修好路径再改工具' });
              return;
            }
            // 一键更新：仓库 + 内容 + 插件，能拉的都拉，拉不了的明说原因。
            // 设计原则：不做任何有损操作（不 stash、不 reset、不强制覆盖），
            // 有任何一项失败都如实报告，不因为某一项失败就跳过其它项。
            if (payload.action === 'updateAll') {
              const liveCfg = readConfig(config);
              const steps = [];

              const repoBefore = gitStatus(root);
              if (!repoBefore.ok) {
                steps.push({ label: '工作台仓库', ok: false, message: repoBefore.error || '读不到仓库状态' });
              } else if (repoBefore.dirty > 0) {
                // 有本地改动时不 pull：--ff-only 会失败，stash 又有丢改动的风险。
                steps.push({
                  label: '工作台仓库',
                  ok: false,
                  skipped: true,
                  message: `本地有 ${repoBefore.dirty} 个文件改动，先提交或 stash 再来更新（不会替你做，怕丢东西）`,
                });
              } else {
                const r = updateGitDir(root, '工作台仓库');
                steps.push({ label: '工作台仓库', ok: r.ok, changed: !!r.changed, message: r.message });
              }

              // 内容层：没配就跳过，不算失败。
              const contentRoot = resolveContentRoot(liveCfg);
              if (!contentRoot) {
                steps.push({ label: '内容层', ok: true, skipped: true, message: '没配独立内容目录，用的是仓库自带的' });
              } else {
                const r = updateContent(liveCfg);
                steps.push({ label: '内容层', ok: r.ok, changed: !!r.changed, message: r.message });
              }

              // 插件：npm 装法才拉得到，本地装法明说无需更新。
              const info = pluginInstallInfo();
              if (!info.updatable) {
                steps.push({
                  label: '插件',
                  ok: true,
                  skipped: true,
                  message: `v${info.version || '?'} ${info.mode}，没有远端可拉（改代码重启即生效）`,
                });
              } else {
                const r = updatePlugin();
                steps.push({ label: '插件', ok: r.ok, changed: !!r.changed, message: r.message });
              }

              const failed = steps.filter((s) => !s.ok);
              const changedAny = steps.some((s) => s.changed);
              const after = gitStatus(root);
              sendJson(res, failed.length ? 400 : 200, {
                ok: failed.length === 0,
                changed: changedAny,
                steps,
                // 有东西变了才需要重启：MCP 是启动时拉起的进程，跑的还是旧代码。
                needRestart: changedAny,
                repo: after.ok ? after : null,
                message: failed.length
                  ? '部分没更新成功，下面写了原因'
                  : changedAny
                    ? '已更新。重启 DSH 才会加载新的工具和插件'
                    : '全是最新，不用动',
              });
              return;
            }

            if (payload.action === 'updateContent') {
              const liveCfg = readConfig(config);
              const result = updateContent(liveCfg);
              sendJson(res, result.ok ? 200 : 400, result);
              return;
            }

            // 更新工作台仓库本体（工具、MCP、插件代码、技能…都在里面）。
            if (payload.action === 'updateRepo') {
              const result = updateGitDir(root, '工作台仓库');
              sendJson(res, result.ok ? 200 : 400, result);
              return;
            }

            if (payload.action === 'updatePlugin') {
              const result = updatePlugin();
              sendJson(res, result.ok ? 200 : 400, result);
              return;
            }

            // 面板里点「重启 DSH」：先把响应发出去，再让进程走掉。
            // 顺序不能反 —— 先 exit 的话浏览器只会看到连接被重置，拿不到任何提示。
            if (payload.action === 'restart') {
              const plan = scheduleRestart();
              sendJson(res, plan.ok ? 200 : 500, plan);
              if (plan.ok) {
                setTimeout(() => process.exit(0), 600);
              }
              return;
            }

            // 只看不拉：fetch 之后告诉面板落后多少个提交、差哪几条。
            if (payload.action === 'checkRepo') {
              sendJson(res, 200, { ok: true, repo: gitStatus(root, { fetch: true }) });
              return;
            }

            const labForPost = typeof getLab === 'function' ? getLab() : null;
            // 面板/小卡片上的 Lab 开关走这里，改的是内存里的运行时状态，
            // 不写磁盘、不重启：关掉立刻停止注入，打开立刻生效。
            if (payload.action === 'lab') {
              if (!labForPost) {
                sendJson(res, 409, { ok: false, error: 'lab 开关没装上' });
                return;
              }
              if (typeof payload.enabled === 'boolean') labForPost.setEnabled(payload.enabled);
              if (typeof payload.active === 'boolean') labForPost.setActive(payload.active);
              sendJson(res, 200, { ok: true, lab: labForPost.snapshot() });
              return;
            }

            const saved = writeUserPath(root, payload.tool, payload.path);
            if (!saved.ok) {
              sendJson(res, 400, saved);
              return;
            }
            sendJson(res, 200, {
              ok: true,
              tools: saved.tools,
              scanned: scanTools(root),
            });
          });
          } catch (error) {
            // 刚才这里抛过一次未捕获异常，直接把整个 dsh 进程带走了。
            // 写个路径而已，出错就回 500，不要牵连宿主。
            console.error('[seep-workbench] 写工具路径失败:', error);
            try {
              sendJson(res, 500, { ok: false, error: '写入失败（看 dsh 日志）' });
            } catch {
              /* 响应可能已经发过 */
            }
          }
          return;
        }

        if (req.method !== 'GET' && req.method !== 'HEAD') {
          sendJson(res, 405, { ok: false, error: 'GET / POST only' });
          return;
        }

        // lab 控制器在 apply() 里才创建，这里用 getter 取，别把它闭包丢了。
        const lab = typeof getLab === 'function' ? getLab() : null;
        // ?skills=1：现问一次技能注册表。更新内容后用它确认新技能有没有被扫到。
        if (/[?&]skills=1/.test(String(req.url ?? ''))) {
          const probeRoot = resolveRoot(readConfig(config));
          probeSkills(ctx, probeRoot, 0)
            .then((found) => sendJson(res, 200, { ok: Boolean(found), skills: found }))
            .catch((error) =>
              sendJson(res, 500, { ok: false, error: error instanceof Error ? error.message : String(error) }),
            );
          return;
        }

        const deep = /[?&]verify=1/.test(String(req.url ?? ''));
        const live = readConfig(config);
        const result = inspect(live);
        const repoRoot = result.repoRoot;
        const python = resolvePython(live);
        const mountedNow = result.ok && existsSync(join(repoRoot, 'Tool', 'mcp', 'seep_mcp_server.py'));
        const wired = mountedNow
          ? ['seep', 'js-reverse', live.enablePlaywright ? 'playwright' : '', live.enableIda ? 'ida' : '', '技能']
              .filter(Boolean)
              .join(' / ')
          : '无';

        sendJson(res, 200, {
          ok: Boolean(mountedNow),
          repoRoot,
          version: result.version,
          python,
          wired,
          labGate: live.labGate,
          lab: lab ? lab.snapshot() : null,
          skillsEnabled: live.enableSkills,
          optionalMcp: { ida: live.enableIda, playwright: live.enablePlaywright },
          content: (() => {
            const root = resolveContentRoot(live);
            return { root, repo: String(live.contentRepo || ''), git: contentStatus(root) };
          })(),
          repoGit: gitStatus(repoRoot),
          plugin: pluginInstallInfo(),
          pluginVersion: selfVersion(),
          deep,
          lines: result.lines,
          tools: result.ok ? toolsFor(repoRoot, python, deep) : {},
        });
        } catch (error) {
          // 宿主把 handler 的异常统一变成 400 空响应，什么线索都不给。
          // 自己兜住并回报具体原因，否则排查只能靠猜。
          console.error('[seep-workbench] 面板接口出错:', error);
          try {
            sendJson(res, 500, {
              ok: false,
              error: `接口出错：${error instanceof Error ? error.message : String(error)}`,
            });
          } catch {
            /* 响应已经发过了 */
          }
        }
      },
    });
  });
}

export function apply(ctx, rawConfig = {}) {
  const config = readConfig(rawConfig);
  const result = inspect(config);
  const repoRoot = result.repoRoot;
  const mounted = { seep: false, jsReverse: false, skills: false };
  let lab = null;
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
        env: resolveContentRoot(config) ? { SEEP_CONTENT_ROOT: resolveContentRoot(config) } : undefined,
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

    if (config.enablePlaywright === true) {
      mountMcp(
        ctx,
        {
          key: 'playwright',
          serverName: 'playwright',
          command: 'npx',
          args: ['-y', '@playwright/mcp@latest'],
          cwd: repoRoot,
          timeoutMs: PLAYWRIGHT_TIMEOUT_MS,
        },
        mounted,
        lines,
      );
    }

    if (config.enableIda === true) {
      const ida = resolveIda(config);
      if (!ida) {
        lines.push(
          '要挂 IDA MCP，但没找到 IDA（设 SEEP_IDA_ROOT，或确认 IDA 目录下有 python311/Lib/site-packages/ida_pro_mcp）。',
        );
      } else {
        mountMcp(
          ctx,
          {
            key: 'ida',
            serverName: 'ida',
            command: ida.python,
            args: [ida.server],
            cwd: repoRoot,
            timeoutMs: IDA_TIMEOUT_MS,
          },
          mounted,
          lines,
        );
      }
    }

    if (config.enableSkills !== false) {
      try {
        // 技能优先读内容目录（如果配了且目录存在），否则用仓库自带的那份。
        const contentRoot = resolveContentRoot(config);
        const contentSkills = contentRoot
          ? [join(contentRoot, 'skill'), join(contentRoot, 'safe-skills')].filter((d) => existsSync(d))
          : [];
        const skillDirs = contentSkills.length
          ? contentSkills
          : [join(repoRoot, 'Tool', 'skill'), join(repoRoot, 'Tool', 'skill', 'safe-skills')];
        ctx.plugin(SkillFilesystem, { customSkillDirs: skillDirs });
        ctx.plugin(ToolSkill, {});
        mounted.skills = true;
      } catch (error) {
        lines.push(
          `挂载技能失败：${error instanceof Error ? error.message : String(error)}`,
        );
      }
    }
  }

  // 纪律正文读一次缓存住；文件没了就降级成「只切状态、不注入正文」。
  // 不管配置里开关是开是关都要读：面板上的开关能随时把它打开，那时得立刻有正文可用。
  let discipline = '';
  const labGate = config.labGate !== false;
  const disciplineFile = join(repoRoot || '', DISCIPLINE_FILE);
  if (repoRoot && existsSync(disciplineFile)) {
    try {
      discipline = readFileSync(disciplineFile, 'utf8');
    } catch {
      discipline = '';
    }
  }
  if (result.ok && !discipline) {
    lines.push(`${DISCIPLINE_FILE} 没读到，lab 开关降级为「只切换状态、不注入正文」。`);
  }
  lab = installLabGate(ctx, { discipline, enabled: labGate, repoRoot });

  const ok = result.ok && mounted.seep;
  if (ok) {
    const wired = [
      mounted.seep ? 'seep' : '',
      mounted.jsReverse ? 'js-reverse' : '',
      mounted.playwright ? 'playwright' : '',
      mounted.ida ? 'ida' : '',
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
      registerPanelApi(ctx, rawConfig, () => lab);
    } catch (error) {
      lines.push(`面板接口没挂上：${error instanceof Error ? error.message : String(error)}`);
    }
  }

  const status = {
    at: new Date().toISOString(),
    ok,
    repoRoot,
    version: result.version,
    python: result.ok ? resolvePython(config) : '',
    mounted,
    skillsEnabled: config.enableSkills !== false,
    optionalMcp: { ida: config.enableIda === true, playwright: config.enablePlaywright === true },
    content: (() => {
      const root = resolveContentRoot(config);
      return { root, git: contentStatus(root), repo: String(config.contentRepo || '') };
    })(),
    skills: null,
    labGate,
    lab: lab ? lab.snapshot() : null,
    lines,
  };
  writeStatus(status);

  // 技能是真注册上了还是只是「调了」，等注册表能答话再补写一次
  if (mounted.skills) {
    probeSkills(ctx, repoRoot).then((found) => {
      if (!found) return;
      writeStatus({ ...status, skills: found, at: new Date().toISOString() });
      console.error(
        `[seep-workbench] 技能注册表：${found.count} 个（${found.names.join(', ') || '空'}）`,
      );
    });
  }

  return { ...result, ok, mounted, lines };
}
