/**
 * lab 开关 —— 每个会话一个状态，默认关闭。
 *
 * 状态只活在内存里：进程退出即销毁，不写磁盘。所以不会残留到第二天，
 * 窗口 A 开了也不影响窗口 B。
 *
 * 两道开关，作用不同：
 *   · enabled  —— 总闸。关掉之后连 `lab：` 口令都不认，什么都不触发。
 *   · active   —— 本会话是否在实验模式（决定纪律正文注不注入）。
 *
 * 三个入口都能改它们：面板/小卡片上的开关（走宿主 API）、对话框里发 `lab：` / `退出实验`。
 *
 * 这个文件刻意不依赖任何 @deepseek-ai/* 包，好处是可以脱离 DSH 单独跑测试
 * （见 test/lab-gate.test.mjs）。
 */

import { createRewriter } from './lab-rewrite.js';

/** 进入实验的口令。只认指令，不认内容 —— 聊到 APK/破解 不构成激活。 */
export const ENTER_PATTERNS = ['lab：', 'lab:', '实验：', '进入实验：'];

/** 退出实验的口令。 */
export const EXIT_PATTERNS = ['退出实验', '退出工作环境', 'exit lab'];

/** 纪律正文在系统提示词里的排序位置：紧跟计划策略之后，早于工具说明。 */
export const DISCIPLINE_SECTION_ORDER = 550;

/** 从一条消息里取出纯文本（跳过图片、工具块等）。 */
export function messageText(message) {
  const blocks = message?.content;
  if (!Array.isArray(blocks)) return '';
  let out = '';
  for (const block of blocks) {
    if (block && block.type === 'text' && typeof block.text === 'string') out += `${block.text}\n`;
  }
  return out;
}

/** 一批消息里有没有口令。返回 'enter' / 'exit' / null。 */
export function classify(messages) {
  let text = '';
  for (const message of messages ?? []) {
    if (message?.source?.kind === 'user') text += messageText(message);
  }
  if (!text) return null;
  const lower = text.toLowerCase();
  if (ENTER_PATTERNS.some((p) => text.includes(p) || lower.includes(p))) return 'enter';
  if (EXIT_PATTERNS.some((p) => text.includes(p) || lower.includes(p))) return 'exit';
  return null;
}

/**
 * 把 lab 开关挂到 ctx 上。
 *
 * @param ctx - Cordis 上下文，需要 on() 方法
 * @param options.discipline - 纪律正文；空串表示降级（只切状态、不注入）
 * @param options.enabled - 总闸初值（默认开）。关掉后口令也不认。
 * @returns 控制器：{ setEnabled, setActive, snapshot, state }
 */
export function installLabGate(ctx, { discipline = '', enabled = true, repoRoot = '' } = {}) {
  // 词表优先读仓库里由 TS 源生成的 sensitive-rules.json —— pi 与 DSH 共用同一份。
  const rewriter = createRewriter({ repoRoot });
  const state = new Map();
  const fibers = new Map();

  // 进程级的总闸与「强制进入」意图。
  // forced=true 表示用户直接用面板/卡片开的，之后新建的会话也应该接着进。
  let masterEnabled = enabled !== false;
  let forced = false;
  let rewriteCount = 0;
  let lastRewrite = null;

  /** 这个会话现在到底算不算在实验模式里。 */
  const isActive = (agent) => masterEnabled && state.get(agent)?.active === true;

  // 每个会话注册一条自己的提示词分节：开=正文，关=空串。
  // 分节注册在 agent 作用域里，所以天然只影响这个会话。
  ctx.on('agent/created', ({ agent }) => {
    state.set(agent, { active: masterEnabled && forced, since: masterEnabled && forced ? Date.now() : 0 });
    const fiber = agent.ctx.inject(['systemPrompt'], (scope) => {
      scope.systemPrompt.section({
        name: 'seep:lab-discipline',
        order: DISCIPLINE_SECTION_ORDER,
        text: () => (isActive(agent) ? discipline : ''),
      });
    });
    fibers.set(agent, fiber);
  });

  // 只观察，不拦消息：永远把决定权交回给后面的监听者。
  ctx.on('agent/pre-step', async ({ agent, messages }, next) => {
    const current = state.get(agent);
    // 总闸关着的时候连口令都不认 —— 「什么都不触发」就应该是真的什么都不触发。
    if (current !== undefined && masterEnabled) {
      const verdict = classify(messages);
      if (verdict === 'enter' && !current.active) {
        current.active = true;
        current.since = Date.now();
      } else if (verdict === 'exit' && current.active) {
        current.active = false;
        current.since = 0;
        // 口令退出时把「强制进入」也撤掉，否则下一个新会话又自动进来
        forced = false;
      }
    }

    const decision = await next();

    // 不在 lab 模式就原样放行；在的话改写进入这一步的消息：
    // 敏感口语词换成合规术语，命中审计词时补一句授权前缀。
    // 口令判定用的是改写前的原文（classify 在 next() 之前已经跑过）。
    if (decision?.kind === 'reject' || !isActive(agent)) return decision;
    const rewritten = rewriter.rewriteMessages(decision.messages ?? messages);
    if (rewritten === (decision.messages ?? messages)) return decision;

    rewriteCount += 1;
    {
      const before = String((decision.messages ?? messages)?.[0]?.content?.[0]?.text ?? '');
      const after = String(rewritten?.[0]?.content?.[0]?.text ?? '');
      lastRewrite = { before: before.slice(0, 200), after: after.slice(0, 240), at: Date.now() };
    }
    // 改写只发生在「发给模型的那份消息」上，界面里看到的仍是原文。
    // 想确认它真的生效，设 SEEP_LAB_DEBUG=1 就能在 dsh 日志里看到前后对比。
    if (process.env.SEEP_LAB_DEBUG) {
      const before = (decision.messages ?? messages)?.[0]?.content?.[0]?.text ?? '';
      const after = rewritten?.[0]?.content?.[0]?.text ?? '';
      console.error('[lab] 改写前: %s', String(before).slice(0, 80));
      console.error('[lab] 改写后: %s', String(after).slice(0, 120));
    }
    return { ...decision, messages: rewritten };
  });

  ctx.on('agent/disposed', ({ agent }) => {
    state.delete(agent);
    const fiber = fibers.get(agent);
    fibers.delete(agent);
    if (fiber !== undefined) {
      // 释放失败不该冒泡成会话错误，吞掉即可。
      Promise.resolve(fiber.dispose?.()).catch(() => {});
    }
  });

  const controller = {
    /** 总闸。关 = 全部归零（已开的会话也立刻停止注入）。 */
    setEnabled(value) {
      masterEnabled = value !== false;
      if (!masterEnabled) {
        forced = false;
        for (const entry of state.values()) {
          entry.active = false;
          entry.since = 0;
        }
      }
      return controller.snapshot();
    },
    /** 手动进入/退出。进入会记成「强制」，新建会话也接着进。 */
    setActive(value) {
      const on = value === true && masterEnabled;
      forced = on;
      for (const entry of state.values()) {
        entry.active = on;
        entry.since = on ? Date.now() : 0;
      }
      return controller.snapshot();
    },
    /** 当前状态（给面板和 API 用）。 */
    snapshot() {
      const agents = [...state.values()];
      return {
        enabled: masterEnabled,
        forced,
        activeSessions: agents.filter((e) => e.active).length,
        sessions: agents.length,
        injecting: masterEnabled && agents.some((e) => e.active),
        hasDiscipline: discipline.length > 0,
        impersonation: { rules: rewriter.rules, fromRepo: rewriter.fromFile },
        rewrites: rewriteCount,
        lastRewrite,
      };
    },
    state,
  };

  return controller;
}
