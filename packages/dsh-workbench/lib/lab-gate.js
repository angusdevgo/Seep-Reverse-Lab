/**
 * lab 开关 —— 每个会话一个状态，默认关闭。
 *
 * 状态只活在内存里：进程退出即销毁，不写磁盘。所以不会残留到第二天，
 * 窗口 A 开了也不影响窗口 B。
 *
 * 这个文件刻意不依赖任何 @deepseek-ai/* 包，好处是可以脱离 DSH 单独跑测试
 * （见 test/lab-gate.test.mjs）。
 */

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
 * @returns {{ state: Map<object, {active:boolean, since:number}> }}
 */
export function installLabGate(ctx, { discipline = '' } = {}) {
  const state = new Map();
  const fibers = new Map();

  // 每个会话注册一条自己的提示词分节：开=正文，关=空串。
  // 分节注册在 agent 作用域里，所以天然只影响这个会话。
  ctx.on('agent/created', ({ agent }) => {
    state.set(agent, { active: false, since: 0 });
    const fiber = agent.ctx.inject(['systemPrompt'], (scope) => {
      scope.systemPrompt.section({
        name: 'seep:lab-discipline',
        order: DISCIPLINE_SECTION_ORDER,
        text: () => (state.get(agent)?.active === true ? discipline : ''),
      });
    });
    fibers.set(agent, fiber);
  });

  // 只观察，不拦消息：永远把决定权交回给后面的监听者。
  ctx.on('agent/pre-step', ({ agent, messages }, next) => {
    const current = state.get(agent);
    if (current !== undefined) {
      const verdict = classify(messages);
      if (verdict === 'enter' && !current.active) {
        current.active = true;
        current.since = Date.now();
      } else if (verdict === 'exit' && current.active) {
        current.active = false;
        current.since = 0;
      }
    }
    return next();
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

  return { state };
}
