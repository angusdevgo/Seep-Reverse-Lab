/**
 * Seep 工作台 —— 面板（浏览器侧）
 *
 * 格式遵循 DSH 客户端模块协议：外层 window.__ModuleLoader__.load 包住，
 * factory(require) 返回 { apply, inject }。不用打包器 —— 只 require('react')，
 * 其余全走 ctx 上的服务。
 *
 * 面板同时挂在两个位置（同一个组件，两处入口）：
 *   1. 设置 → 插件 → seep-dsh-workbench → 我们那一行的「配置」
 *      （plugins.row.config，DSH 官方给 bundle row 的配置位；宿主会传 form 进来）
 *   2. 设置 → Seep 工作台（settings.section，独立一页，方便直接找到）
 *
 * 面板显示什么：
 *   · 现在挂没挂上（宿主侧 /seep-workbench/api 提供，浏览器读不到磁盘）
 *   · 工作台路径 / Python / 技能开关 / lab 开关（写回宿主配置）
 *   · 工具清单：哪个找到、哪个缺
 */

window.__ModuleLoader__.load({
  id: 'seep-dsh-workbench',
  factory: (require) => {
    const React = require('react');
    const h = React.createElement;

    const NS = 'seep-workbench';
    const ENTRY_ID = 'seep-workbench-boot';
    const API = '/seep-workbench/api';

    // keyed slot 的 key 是 `<包名>#<行 id>`，这是 DSH 的约定。
    const ROW_KEY = 'seep-dsh-workbench#seep-workbench-boot';

    async function fetchStatus(deep) {
      const res = await fetch(deep ? `${API}?verify=1` : API, {
        method: 'GET',
        credentials: 'same-origin',
      });
      if (!res.ok) throw new Error(`接口返回 ${res.status}`);
      return res.json();
    }

    // ---------------------------------------------------------------- 样式
    // 全用内联样式 + DSH 的设计变量：不引入样式表，少一处要跟着前端版本维护的东西。
    const S = {
      page: { display: 'flex', flexDirection: 'column', gap: 16, maxWidth: 820 },
      card: {
        border: '0.5px solid var(--dsw-alias-border-l3)',
        borderRadius: 16,
        background: 'var(--dsw-alias-settings-card-fill, var(--dsw-alias-bg-layer-2))',
        padding: '14px 16px',
        display: 'flex',
        flexDirection: 'column',
        gap: 12,
      },
      cardTitle: { fontSize: 14, fontWeight: 500, display: 'flex', alignItems: 'center', gap: 10 },
      row: { display: 'flex', gap: 10, alignItems: 'center' },
      rowLabel: { fontSize: 13, color: 'var(--dsw-alias-label-secondary)', minWidth: 92, flex: 'none' },
      input: {
        boxSizing: 'border-box',
        flex: 1,
        minWidth: 0,
        height: 32,
        padding: '0 10px',
        fontSize: 13,
        color: 'var(--dsw-alias-label-primary)',
        background: 'var(--dsw-alias-bg-layer-1)',
        border: '0.5px solid var(--dsw-alias-border-l4)',
        borderRadius: 8,
        fontFamily: 'var(--ds-font-family-code, monospace)',
      },
      btn: {
        height: 32,
        padding: '0 14px',
        fontSize: 13,
        borderRadius: 8,
        cursor: 'pointer',
        border: '0.5px solid var(--dsw-alias-border-l3)',
        background: 'transparent',
        color: 'var(--dsw-alias-label-primary)',
        flex: 'none',
      },
      btnPrimary: {
        height: 32,
        padding: '0 16px',
        fontSize: 13,
        borderRadius: 8,
        cursor: 'pointer',
        border: 'none',
        background: 'var(--dsw-alias-button-primary-fill)',
        color: 'var(--dsw-alias-label-primary-foreground)',
        flex: 'none',
      },
      hint: { fontSize: 12, lineHeight: '18px', color: 'var(--dsw-alias-label-tertiary)', margin: 0 },
      err: { fontSize: 12, lineHeight: '18px', color: 'var(--dsw-alias-state-error-primary)', margin: 0 },
      okc: { fontSize: 12, lineHeight: '18px', color: 'var(--dsw-alias-state-success-primary)', margin: 0 },
      list: { listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column' },
      item: {
        display: 'grid',
        gridTemplateColumns: '16px 104px 74px 1fr',
        alignItems: 'center',
        gap: 8,
        fontSize: 12.5,
        lineHeight: '20px',
        padding: '3px 0',
        borderBottom: '0.5px solid var(--dsw-alias-border-l1)',
      },
      mono: { fontFamily: 'var(--ds-font-family-code, monospace)' },
    };

    const GLYPH = { READY: '✅', DEGRADED: '⚠️', OPTIONAL: '○', MISSING: '❌', UNKNOWN: '?' };
    const COLOR = {
      READY: 'var(--dsw-alias-state-success-primary)',
      DEGRADED: 'var(--dsw-alias-state-warn-label)',
      OPTIONAL: 'var(--dsw-alias-label-tertiary)',
      MISSING: 'var(--dsw-alias-state-error-primary)',
      UNKNOWN: 'var(--dsw-alias-label-tertiary)',
    };

    // ---------------------------------------------------------------- 组件

    /**
     * 面板本体。两种入口传进来的东西不一样：
     *   · plugins.row.config：宿主直接给 form = { state, mutate }
     *   · settings.section ：自己从 ctx.configForms 取
     * 所以先看 props.form，没有就退回 ctx。
     */
    function makePanel(ctx) {
      return function SeepWorkbenchPanel(props) {
        // 两个入口传进来的 form 形状不一样：
        //   · plugins.row.config：宿主给 { state, mutate }（只读快照 + 写操作）
        //   · settings.section ：我们自己的 ConfigForm（getSnapshot/subscribe/mutate）
        // 统一成「一个快照 + 一个 mutate」，两种都能用。
        //
        // 注意：ConfigForm 必须**每次渲染重新取**。保存后 profile 会重载，
        // 旧的控制器会被销毁，拿旧对象再写就会报错（实测：writeGeneration undefined）。
        const hostForm = (props && props.form) || null;
        const cf = hostForm ? null : ctx.configForms.get(ENTRY_ID);
        const view = (props && props.view) || 'page';

        const [selfSnap, setSelfSnap] = React.useState(() => (cf ? cf.getSnapshot() : null));
        React.useEffect(() => {
          if (!cf) return undefined;
          const sync = () => setSelfSnap(cf.getSnapshot());
          sync();
          return cf.subscribe(sync);
        }, [cf]);

        const snap = hostForm ? hostForm.state : selfSnap;
        const mutate = hostForm ? hostForm.mutate : cf && cf.mutate;

        const [status, setStatus] = React.useState(null);
        const [statusError, setStatusError] = React.useState('');
        const [busy, setBusy] = React.useState(false);
        const [notice, setNotice] = React.useState('');

        const load = React.useCallback((deep) => {
          setBusy(true);
          fetchStatus(deep)
            .then((data) => {
              setStatus(data);
              setStatusError('');
            })
            .catch((e) => setStatusError(String((e && e.message) || e)))
            .finally(() => setBusy(false));
        }, []);

        React.useEffect(() => {
          load(false);
        }, [load]);

        const value = (snap && snap.value) || {};
        const [root, setRoot] = React.useState(value.repoRoot || '');
        const [python, setPython] = React.useState(value.pythonPath || '');
        const [skills, setSkills] = React.useState(value.enableSkills !== false);
        const [labGate, setLabGate] = React.useState(value.labGate !== false);

        // 宿主值变了就同步草稿（按 revision，避免把正在输入的字冲掉）
        React.useEffect(() => {
          const v = (snap && snap.value) || {};
          setRoot(v.repoRoot || '');
          setPython(v.pythonPath || '');
          setSkills(v.enableSkills !== false);
          setLabGate(v.labGate !== false);
        }, [snap && snap.revision]);

        const saved = value;
        const dirty =
          root !== (saved.repoRoot || '') ||
          python !== (saved.pythonPath || '') ||
          skills !== (saved.enableSkills !== false) ||
          labGate !== (saved.labGate !== false);

        const save = async () => {
          setBusy(true);
          setNotice('');
          try {
            const ops = [
              { op: 'set', path: ['repoRoot'], value: root.trim() },
              { op: 'set', path: ['pythonPath'], value: python.trim() },
              { op: 'set', path: ['enableSkills'], value: skills },
              { op: 'set', path: ['labGate'], value: labGate },
            ];
            let okAccepted;
            try {
              okAccepted = await mutate(ops);
            } catch (first) {
              // 控制器可能刚被换代（保存后 profile 重载），重新取一次再试
              const fresh = ctx.configForms.get(ENTRY_ID);
              okAccepted = await fresh.mutate(ops);
            }
            setNotice(okAccepted ? '已保存，重启 DSH 后生效' : '宿主拒绝了这次修改（路径可能不合法）');
            if (okAccepted) load(false);
          } catch (e) {
            setNotice(`保存失败：${(e && e.message) || String(e)}`);
          } finally {
            setBusy(false);
          }
        };

        if (!snap) {
          return h('span', { style: { fontSize: 13, color: 'var(--dsw-alias-label-tertiary)' } }, 'Seep 工作台');
        }

        // 摘要视图：插件列表里那一行只用一句话（注意 form 来自 props，不是快照）
        if (view === 'summary') {
          const okNow = status && status.ok;
          return h(
            'span',
            { style: { fontSize: 13, color: okNow ? 'var(--dsw-alias-label-primary)' : 'var(--dsw-alias-label-secondary)' } },
            status
              ? okNow
                ? `已就绪 · ${status.wired || '未接线'}`
                : '未就绪 · 点开配置'
              : 'Seep 工作台',
          );
        }

        // ---- 状态卡
        const statusCard = h(
          'div',
          { style: S.card },
          h('div', { style: S.cardTitle }, '运行状态'),
          statusError
            ? h('p', { style: S.err }, `读不到状态：${statusError}（宿主侧接口没起来？）`)
            : !status
              ? h('p', { style: S.hint }, '正在读取…')
              : h(
                  'div',
                  { style: { display: 'flex', flexDirection: 'column', gap: 6 } },
                  h(
                    'div',
                    { style: { display: 'flex', alignItems: 'center', gap: 10, fontSize: 14 } },
                    h('span', { style: { color: status.ok ? COLOR.READY : COLOR.MISSING } },
                      status.ok ? '● 就绪' : '● 未就绪'),
                    h('span', { style: { ...S.hint, fontSize: 12 } }, `仓库版本 ${status.version || '未知'}`),
                    h('span', { style: { ...S.hint, fontSize: 12 } }, `已接线：${status.wired || '无'}`),
                  ),
                  status.repoRoot
                    ? h('p', { style: S.hint }, '当前工作台：', h('code', { style: S.mono }, status.repoRoot))
                    : null,
                  ...(status.lines || []).map((line, i) =>
                    h('p', { key: i, style: status.ok ? S.hint : S.err }, line),
                  ),
                ),
        );

        // ---- 配置卡
        const configCard = h(
          'div',
          { style: S.card },
          h('div', { style: S.cardTitle }, '配置'),
          h(
            'div',
            { style: S.row },
            h('span', { style: S.rowLabel }, '工作台路径'),
            h('input', {
              style: S.input,
              value: root,
              spellCheck: false,
              placeholder: 'C:\\path\\to\\Seep-Reverse-Lab',
              onChange: (e) => setRoot(e.target.value),
            }),
          ),
          h(
            'div',
            { style: S.row },
            h('span', { style: S.rowLabel }, 'Python'),
            h('input', {
              style: S.input,
              value: python,
              spellCheck: false,
              placeholder: '留空自动找（按 setup/tool-registry.json 的候选链）',
              onChange: (e) => setPython(e.target.value),
            }),
          ),
          h(
            'label',
            { style: { display: 'flex', gap: 8, alignItems: 'center', fontSize: 13 } },
            h('input', { type: 'checkbox', checked: skills, onChange: (e) => setSkills(e.target.checked) }),
            '在 DSH 里列出 10 个技能',
          ),
          h(
            'label',
            { style: { display: 'flex', gap: 8, alignItems: 'center', fontSize: 13 } },
            h('input', { type: 'checkbox', checked: labGate, onChange: (e) => setLabGate(e.target.checked) }),
            '启用 lab 开关（只有消息里出现 lab： 才注入作战纪律）',
          ),
          h(
            'div',
            { style: { ...S.row, marginTop: 2 } },
            h('button', { style: dirty ? S.btnPrimary : S.btn, disabled: busy || !dirty, onClick: save },
              dirty ? '保存' : '已保存'),
            notice ? h('span', { style: notice.startsWith('已保存') ? S.okc : S.err }, notice) : null,
            h('span', { style: { ...S.hint, marginLeft: 'auto' } }, '改完需要重启 DSH 才生效'),
          ),
        );

        // ---- 工具清单
        const tools = status && status.tools ? Object.entries(status.tools) : [];
        const toolCard = tools.length === 0 ? null : h(
          'div',
          { style: S.card },
          h(
            'div',
            { style: S.cardTitle },
            '工具清单',
            h('span', { style: { ...S.hint, fontSize: 12, fontWeight: 400 } },
              status.deep ? '深度检测：真跑过一次' : '快速检查：只看找没找到'),
            h(
              'div',
              { style: { marginLeft: 'auto', display: 'flex', gap: 8 } },
              h('button', { style: S.btn, disabled: busy, onClick: () => load(false) }, '重新检查'),
              h('button', { style: S.btn, disabled: busy, title: '会真的启动每个工具验一下，慢一些',
                onClick: () => load(true) }, '深度检测'),
            ),
          ),
          h(
            'ul',
            { style: S.list },
            tools.map(([id, t]) =>
              h(
                'li',
                { key: id, style: S.item },
                h('span', null, GLYPH[t.state] || '?'),
                h('span', { style: S.mono }, id),
                h('span', { style: { color: COLOR[t.state] || 'inherit', fontSize: 11.5 } }, t.state),
                h('span', {
                  style: {
                    color: 'var(--dsw-alias-label-tertiary)',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  },
                  title: t.detail || t.path || '',
                }, t.detail || t.path || ''),
              ),
            ),
          ),
          h('p', { style: S.hint }, '缺的不是核心项（○ OPTIONAL）就不用管；❌ MISSING 才要装。'),
        );

        // ---- 兜底说明卡
        const tipCard = h(
          'div',
          { style: S.card },
          h('div', { style: S.cardTitle }, '想更彻底地查？'),
          h('p', { style: S.hint }, '面板只做快速判断。要真正确认每个工具都能跑，在仓库目录执行：'),
          h(
            'code',
            {
              style: {
                ...S.mono,
                fontSize: 12,
                lineHeight: '20px',
                padding: '8px 10px',
                borderRadius: 8,
                background: 'var(--dsw-alias-bg-layer-1)',
                border: '0.5px solid var(--dsw-alias-border-l1)',
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-all',
              },
            },
            'python setup/verify-dsh.py\npython Tool/mcp/tool_resolver.py --verify',
          ),
        );

        return h('div', { style: S.page }, statusCard, configCard, toolCard, tipCard);
      };
    }

    // ---------------------------------------------------------------- 入口

    /** 这半侧需要的客户端服务。 */
    const inject = ['slots', 'configForms'];

    function apply(ctx) {
      const Panel = makePanel(ctx);

      // 入口一：设置 → 插件 → 我们的卡片 → 那一行的「配置」。
      // DSH 官方给 bundle row 的配置位，宿主会把 form 传进来。
      // 注意：keyed 槽位用 key（不是 id），值是 `<包名>#<行 id>`。
      ctx.slots.inject('plugins.row.config', () =>
        ctx.slots.register(
          {
            name: 'plugins.row.config',
            key: ROW_KEY,
            order: 10,
            label: () => 'Seep 工作台',
          },
          Panel,
        ),
      );

      // 入口二：设置左侧导航里单独一页，不用翻插件列表也能找到。
      // 这一处宿主不传 form，组件会退回 ctx.configForms.get()。
      ctx.slots.inject('settings.section', () =>
        ctx.slots.register(
          { name: 'settings.section', id: NS, order: 40, label: () => 'Seep 工作台' },
          Panel,
        ),
      );
    }

    return { apply, inject, NS };
  },
});
