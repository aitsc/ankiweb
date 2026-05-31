# ankiweb — Spec 1：共享地基 (Foundation A) + 学习闭环 (Study Loop C)

- 日期：2026-05-31
- 状态：已批准，待转实现计划 (writing-plans)
- 作者：tsc + Claude
- 适用范围：本 spec 只覆盖**子项目 A（共享地基）**与**子项目 C（学习闭环 UI）**；AnkiConnect API (B)、Browser/Editor (D)、其余界面 (E) 各自单独立 spec。

---

## 0. 背景与总目标

把 Anki 桌面端"翻译式"复刻为一个浏览器应用 **ankiweb**，两大能力：(1) 在网页上复刻 Anki 桌面端界面与交互；(2) 复刻 AnkiConnect 的全部 HTTP API 增删改查。**不实现同步 (sync) 与插件 (add-ons)。**

后端基于 `pip install anki`（pylib）+ FastAPI。前端策略（已选定）：**复用 Anki 真实编译前端，并把 Anki 内部 web 服务器 `qt/aqt/mediasrv.py` 与 webview 的 `pycmd`/`bridgeCommand`/`web.eval` 桥接翻译进 FastAPI（HTTP + WebSocket）。** Qt-only 的部分（主窗口外壳、顶栏菜单、Browser 表格、Add/Edit 对话框）以 web 重建来承载真实页面。

部署形态（已选定）：**单用户本地优先**——进程内单个 collection、无账号、无并发隔离、运行在本机由浏览器打开，等价于"把桌面 Anki 搬进浏览器"。

### 0.1 版本锁定（已验证）

- `anki==25.9.4`（wheel `cp39-abi3` manylinux，兼容 Python 3.12）。已确认 wheel 含：`anki/_rsbridge.so`（原生 PyO3 后端，29MB）、`anki/_backend_generated.py`（全部 RPC 的 `name()`/`name_raw()`，110KB）、`anki/_fluent.py`、`anki/buildinfo.py`、24 个 `*_pb2.py`（含 `.pyi`）。
- `aqt==25.9.4`（`py3-none-any`）。已确认 wheel 含完整编译前端 `_aqt/data/web/`：`sveltekit/`（`index.html` + `_app/immutable/…`，105 项）、`pages/congrats.{html,js,css}`、`pages/editable.{js,css}`、`js/reviewer.js`(522KB)、`js/editor.js`(3.5MB)、`js/reviewer-bottom.js`、`js/deckbrowser.js`、`js/toolbar.js`、`js/mathjax.js`、`js/webview.js`、`css/{reviewer,reviewer-bottom,toolbar,toolbar-bottom,deckbrowser,overview,editor,editable,webview}.css`、`js/vendor/{jquery,jquery-ui,bootstrap,plot,mathjax/*}`、`imgs/*`。
- **关键约束**：`_rsbridge.so` 的 buildhash 必须与 `anki.buildinfo.buildhash` 匹配，导入时校验（不匹配即抛错）；故 `anki` 与提取自 `aqt` 的前端资源必须**严格同版本**。

### 0.2 非目标（本 spec 之外）

- 子项目 B（AnkiConnect API）、D（Browser + Editor）、E（deck options / stats / change-notetype / 导入导出 / custom study / 过滤牌组 / 图像遮挡）。
- 同步 (sync)、共享牌组、AnkiWeb 账号、v2→v3 调度升级、插件/add-on（连同 `addonManager` 配置——改用普通配置文件）。
- **本 spec 内暂缓**：TTS 语音合成、录音 (`record_audio`)。（`[sound:]` 音频用 HTML5 `<audio>` 播放，**保留**。）

### 0.3 本 spec 交付

可日常使用的核心学习流程：打开本机 collection → 浏览器看到牌组列表与到期计数 → 进入某牌组 Overview → Study Now → Reviewer 显示问题/答案、四个难度按钮（含间隔预览）、type-in-answer、`[sound:]` 播放、自定义调度 (cardStateCustomizer)、auto-advance → 答题后计数刷新 → 学完显示 congrats。底层同时落地后续所有子项目都依赖的"脊柱"。

---

## 1. 架构总览

自底向上的分层"脊柱"（本 spec 落地全部 6 层，其中特性层只做学习闭环 C）：

```
┌─ 特性层 ────────────────────────────────────────────────┐
│ [本 spec] 学习闭环：DeckBrowser · Overview · Reviewer · Congrats │
│ [后续]    AnkiConnect API(B) · Browser/Editor(D) · 其余界面(E)    │
├─ Web 外壳 (§6)：页面引导 · 顶栏 · 客户端路由 · 右键菜单/模态/快捷键原语 │
├─ 桥接层 (§5)：WebSocket — pycmd 上行 + eval/call 下推 + evalWithCallback │
│              + domDone 握手/动作队列 + OpChanges→刷新广播 + JS shim       │
├─ /_anki/* protobuf RPC 层 (§4)：POST 透传 col._backend.<m>_raw          │
│              + 自定义处理器(congratsInfo/调度状态/i18n/customColours)     │
├─ 资源管线 (§3)：vendored _aqt/data/web/ 静态服务(复刻 mediasrv 规则)      │
│              + media 从 col.media.dir()                                  │
├─ 运行时 & Collection 服务 (§2)：单 Collection(server=False)              │
│              + 单 worker 串行执行器 + OpChanges 事件总线                  │
└──────────────────────────────────────────────────────────┘
```

模块边界（每个单元职责单一、接口清晰、可独立测试）：

| 单元 | 职责 | 依赖 | 对外接口 |
|---|---|---|---|
| `collection_service` | 持有并串行化 Collection 访问 | `anki` 包 | `run(fn)`、`backend_raw(method,bytes)`、`open/close`、`subscribe_opchanges(cb)` |
| `assets` | vendored 前端资源静态服务 | `web_assets/` | FastAPI 路由 `/_anki/<path>` 与 media |
| `anki_rpc` | `/_anki/{method}` protobuf 调度 | `collection_service` | POST 路由 + 处理器注册表 |
| `bridge` | WebSocket 双向桥 + JS shim | `collection_service`、各 screen 的 handler | `/ws`、`push_eval/push_call`、`broadcast_opchanges` |
| `shell` | Web 外壳（TS，esbuild 打包） | `bridge`、`assets` | 浏览器页面 |
| `screens/deckbrowser`、`/overview`、`/reviewer`、`/congrats` | 学习闭环各屏（HTML 生成器 + bridge handler + 复用 bundle） | 以上各层 | screen handler + 渲染 |

---

## 2. 运行时 & Collection 服务（子项目 A）

### 2.1 生命周期

- 启动：`col = Collection(path, server=False)`（`anki.collection.Collection`，`collection.py:144`）。`server=False` 自动创建 `<name>.media` 目录、USN=-1（桌面语义）。库文件不存在则后端自动创建。
- 关闭：`col.close(downgrade=False)`；进程退出前调用。
- 保存：**自动**——`col.save()/flush()` 已废弃为 no-op，每个变更 RPC 自带事务。无需手动提交。
- collection 路径：从配置（默认 `~/.local/share/ankiweb/collection.anki2` 或项目配置项），单用户单库。

### 2.2 并发模型（关键约束）

侦察确认：Rust 后端用 `Mutex<Option<Collection>>` 串行化所有 collection 操作（`rslib/src/backend/mod.rs`），PyO3 桥 `py.allow_threads` 释放 GIL；**但 pylib 的 `Collection`/`Note`/`Card`/`ModelManager._cache` 等 Python 对象非线程安全**。

设计：

- 全局**单个** Collection 实例，进程生命周期内常开。
- 所有 collection 访问经 **`ThreadPoolExecutor(max_workers=1)` + 一把 `asyncio.Lock`** 串行化（FastAPI handler 里 `await loop.run_in_executor(single_worker, fn)`，外加 lock 防止 worker 内重入）。
- 理由：(a) 避免 Python 端对象竞争；(b) 长任务（FSRS/graphs/导入）释放 GIL，不阻塞事件循环；(c) 与后端的串行语义一致。
- 长任务进度：`col.latest_progress()`→`Progress` proto，经 WS 推送；取消用 `col.set_wants_abort()`。
- `_backend.py` 在后端调用阻塞主线程 >200ms 时告警——长任务务必走 worker。

### 2.3 OpChanges 事件总线

- 每个变更操作返回 `OpChanges`（`collection_pb2`），含布尔位：`card / note / deck / notetype / tag / config / browser_table / browser_sidebar / note_text / study_queues / kind`。
- `collection_service` 提供 `subscribe_opchanges(callback)`；每次变更操作完成后，把 `OpChanges` 投递给订阅者（主要是 `bridge`，广播给前端）。
- 需携带 **initiator id**（发起方标识），使"发起变更的那个屏幕"能忽略自己触发的刷新（复刻 Anki `operation_did_execute` 的 `initiator` 语义，避免自我重载抖动）。

---

## 3. 资源管线（子项目 A）

### 3.1 资源获取（vendoring，避免运行时 PyQt6）

- 构建期脚本 `tools/fetch_web_assets.py`：`pip download aqt==<pin> --no-deps` → 解压取出 `_aqt/data/web/` → 落到 `ankiweb/web_assets/`（纳入版本控制或由 CI 生成；版本与 `anki` 对齐）。
- **不 `pip install aqt`**（其依赖含 PyQt6，重且无用）；仅取静态资源，运行时零 Qt 依赖。
- 校验：脚本断言关键文件存在（`js/reviewer.js`、`sveltekit/index.html`、`css/reviewer.css`…），并记录版本号到 `web_assets/VERSION` 供启动期与 `anki.buildinfo` 比对告警。

### 3.2 静态服务（复刻 `mediasrv` 解析规则）

复刻 `mediasrv.py` 的路径解析（`_extract_internal_request`/`_handle_builtin_file_request`，§参见 recon mediasrv 文档）：

1. `/_anki/<path>` → `web_assets/<path>`。
2. SvelteKit 页（路径首段 ∈ 白名单 `graphs/congrats/card-info/change-notetype/deck-options/import-anki-package/import-csv/import-page/image-occlusion`）→ 重写到 `sveltekit/…`；`_app/...` 同理。
3. SPA 回退：`sveltekit/<非 immutable 路径>` → 返回 `sveltekit/index.html`；`immutable` 资源 `Cache-Control: max-age=31536000`。
4. 旧版页：`GET /_anki/pages/<name>.html` → `web_assets/pages/<name>.html`。
5. 顶层重映射：裸 `.css`→`css/`；裸 `.js`→`js/`（`jquery`/`jquery-ui`/`plot`→`js/vendor/`）。
6. MIME：照搬 `_mime_for_path` 表。缓存：`.css` 10s、`.js` 0、其余 1h。
7. **media**：未命中的路径 → `col.media.dir()` 下文件，含目录穿越防护（`realpath` 前缀校验）、range/conditional 请求。

### 3.3 i18n 引导

- 前端各页 `setupGlobalI18n()` → `POST /_anki/i18nResources`（body proto `I18nResourcesRequest{modules}`，返回 `generic.Json` 字节，前端自行 `JSON.parse` 并构建 `FluentBundle`）。
- 服务端：透传 `col._backend.i18n_resources_raw(body)`。无需任何重格式化。

---

## 4. `/_anki/*` protobuf RPC 层（子项目 A，翻译 `mediasrv`）

### 4.1 调度与响应约定

- 路由 `POST /_anki/{method}`，`method` 为 camelCase。读取原始 body 字节，按注册表分发。
- 响应：非空字节 → `Response(content=bytes, media_type="application/binary")`；空 → `204`；异常 → `500` + `str(exc)` 纯文本。**照搬 mediasrv 行为以兼容前端 `post.ts` 的错误处理。**
- 命名映射 `snake_case ↔ camelCase` 必须与 `stringcase.camelcase`/Rust `to_camel_case` 一致（注意 `i18n` 等缩写边界，测试覆盖）。

### 4.2 纯透传处理器（注册表）

对一组后端方法，`POST /_anki/<camel>` → `col._backend.<snake>_raw(body)` 直接返回。本 spec 学习闭环至少需要（其余在 B/D/E 扩充）：

| camelCase URL | 后端方法 | 用途 |
|---|---|---|
| `i18nResources` | `i18n_resources_raw` | 前端 i18n（所有页必需） |
| `getCustomColours` | `get_custom_colours_raw` | 主题色 |
| `latestProgress` | `latest_progress_raw` | 进度轮询 |
| `congratsInfo` | `congrats_info_raw` | congrats 页数据（桌面版因 `moveToState` 副作用才走自定义；我们去掉副作用后即纯透传，对应 `SchedulerService.CongratsInfo`） |

> 说明：透传清单应以"前端真正会 POST 的方法"为准；实现时对照 `mediasrv.py:659-701` 的 `exposed_backend_list` 起步，按页面实际网络请求增补。

### 4.3 自定义处理器（重写为 pylib 操作，去 Qt）

学习闭环需要的自定义处理器：

| URL | 行为（去掉 Qt 副作用后） |
|---|---|
| `getSchedulingStatesWithContext` | 由**我们的 reviewer 状态机**产出：`{states = 当前卡的 SchedulingStates, context = SchedulingContext{deck_name, seed}}`（数据源 `col.sched.get_queued_cards()` 的队列项已含 states/context）。**非后端方法**（`FrontendService` 在 pylib 不生成）。 |
| `setSchedulingStates` | `SetSchedulingStatesRequest{key, states}`；**仅当 `key == 本会话 _state_mutation_key`** 时写入 reviewer 的 `_v3.states`（自定义调度用）。 |
| `saveCustomColours` | 写 `col.set_config("customColorPickerPalette", …)`；去掉 `QColorDialog`。 |

### 4.4 安全

- 保留 **`Content-Type: application/binary`** 检查（POST 非该类型 → 403，CSRF/不透明跨源防护）与 **Host 守卫**（`Host` 须以 `127.0.0.1:`/`localhost:`/`[::1]:` 开头）。
- 单用户、同源（前端与 FastAPI 同 origin，`/_anki/...` 相对路径天然可用），**免 bearer key**（Qt 的 `AuthInterceptor`/`_APIKEY` 是 Qt 专有，不复刻）。
- 默认 bind `127.0.0.1:<port>`。

---

## 5. 桥接层（子项目 A，唯一净新增）

Anki 全程**无 WebSocket**：JS→Python 是 Qt QWebChannel 的 `pycmd`，Python→JS 是进程内 `page.runJavaScript`。浏览器里后端够不到页面，故用 **WebSocket** 复刻。

### 5.1 连接与消息协议

- **每页一条 WS**：`/ws?context=<deckbrowser|overview|reviewer|congrats>`。服务端按 context 维护 handler 与"UI 状态镜像"（后续 gui* 动作会读它）。
- 消息（JSON）：
  - **上行 cmd（pycmd）**：`{type:"cmd", id, ctx, arg}`。`arg` 为单个字符串（复刻 Anki 的字符串协议，如 `"ease3"`、`"open:1623"`、`"collapse:3"`、`"key:0:<nid>:<html>"`）。服务端按 ctx 派发到对应 `_linkHandler` 等价物。需回调者回 `{type:"result", id, value}`（JSON）。
  - **下推 eval**：`{type:"eval", id?, js}`（复刻 `web.eval`）。`evalWithCallback` 用 `id` 回程：浏览器执行后回 `{type:"result", id, value}`。
  - **下推 call（偏好）**：`{type:"call", id?, fn, args}`——命名函数调用（如 `fn:"_showQuestion", args:[q,a,bodyclass]`），客户端 shim 按名分发到页面 bundle 暴露的全局函数。**优先 call 而非裸 eval**（减少注入面），仅在必须时用 eval。
  - **刷新**：`{type:"opchanges", flags, initiator}`——OpChanges 广播；前端按位失效重绘，`initiator` 等于自己则忽略。
- 服务端 `bridge` 提供 `push_eval(ctx, js)`、`push_call(ctx, fn, args)`、`eval_with_callback(ctx, js)->awaitable`、`broadcast_opchanges(flags, initiator)`。

### 5.2 注入的 JS shim（页面 bundle 之前加载）

- 定义 `window.pycmd = window.bridgeCommand = function(arg, cb){…通过 WS 发送 {type:"cmd",arg,id}; 若有 cb 则登记 id→cb，收到 result 时 cb(JSON.parse-后的 value)…}`，返回 `false`（兼容内联 `href` 处理器）。
- 复刻 **`domDone` 握手 + 动作队列**：页面就绪前缓冲服务端的 eval/call，收到页面 `pycmd("domDone")` 后 flush。
- 客户端维护 `id→callback` 表（双向 result 关联），并暴露按 `fn` 名分发的 `call` 处理。
- 处理 `#night` hash 约定（夜间模式）。

### 5.3 自定义调度的会话密钥

- 复刻 reviewer 的 per-session 64-bit `_state_mutation_key`（`reviewer.py:162`），作为自定义调度的 CSRF 式守卫：传入 `RUN_STATE_MUTATION` JS（`anki.mutateNextCardStates(key, transform)`），`setSchedulingStates` 校验 key 匹配才写入。

---

## 6. 学习闭环界面（子项目 C，复用真实前端 + 复刻生成器）

> 通用：deckbrowser/overview 在桌面是**服务端 Python 生成 HTML**（f-string/`%`-format + `tr.*` Fluent），reviewer 用编译好的 `reviewer.js`。本 spec **服务端复刻这些 HTML 生成器**（逐字移植），并复用对应 `css/js` bundle；交互经 §5 桥接。

### 6.1 Deck Browser（`screens/deckbrowser`）

- 数据：`col.sched.deck_due_tree()`→`DeckTreeNode`（含 `deck_id/name/level/collapsed/new_count/learn_count/review_count/filtered/children`）、`col.decks.get_current_id()`、`col.studied_today()`、`col.v3_scheduler()`（假定 v3，去掉升级 callout）。
- HTML 生成器移植：`_render_deck_node`/`_renderDeckTree`/`_topLevelDragRow`/`_renderStats`/`_body`（参见 recon deckbrowser 文档，含列：Deck/New/Learn/Review/opts；折叠 `±`；缩进；`current` 高亮；齿轮 `/_anki/imgs/gears.svg`）。
- 复用资源：`css/deckbrowser.css`、`js/deckbrowser.js`、`js/vendor/jquery{,-ui}.min.js`。
- bridge 命令：`open:<id>`（`col.decks.set_current`→导航 overview）、`opts:<id>`（→ Web 右键菜单：Rename/Options/Export/Delete）、`collapse:<id>`（`col.decks.set_collapsed(scope=REVIEWER)`）、`create`（`col.decks.add_normal_deck_with_name`，名字走 Web 输入框）、`drag:<src>,<tgt>`（`col.decks.reparent`；HTML5 拖拽产生该命令，目标空=顶层）、`select:<id>`（shift 选中不打开）。`shared`/`import`/`v2upgrade*` 本 spec 略（import 属 E）。
- 齿轮 `QMenu` → Web 右键菜单（§6.5 原语）。

### 6.2 Overview（`screens/overview`）

- 数据：`col.sched.counts()`→(new,learn,review)、`col.decks.current()`、`col.sched.deck_due_tree(current_id)`（算 buried 差值）、`col.sched._is_finished()`、`col.sched.have_buried()`、`col.render_markdown(desc)`。
- 若 `_is_finished()` → 显示 congrats（§6.4）。否则移植 `_body`/`_desc`/`_table`（New/Learning/Review + buried `±N` + Study Now 按钮）。复用 `css/overview.css`、jquery。
- bridge 命令：`study`（`col.startTimebox()`→导航 review）、`opts`（→ deck options，属 E，本 spec 占位）、`refresh`/`empty`（过滤牌组 `rebuild/empty_filtered_deck`）、`studymore`/`customStudy`（custom study，属 E，占位）、`unbury`（`col.sched.unbury_deck`，模式选择走 Web 模态）、`description`（编辑描述，属 E/占位）、`http*`（新标签打开）。

### 6.3 Reviewer（`screens/reviewer`）—— 本 spec 的核心

- **初始化**：复刻 `_initWeb`，加载 `css/reviewer.css` + `js/mathjax.js` + `js/vendor/mathjax/tex-chtml-full.js` + `js/reviewer.js`；底栏加载 `css/reviewer-bottom.css` + `css/toolbar-bottom.css` + jquery + `js/reviewer-bottom.js`。复刻 `revHtml()` 静态骨架（`#_mark`/`#_flag`/`#qa`）。
- **取卡**：`col.sched.get_queued_cards(fetch_limit=1)`→`QueuedCards`；空则进 congrats（overview finished）。`Card(col, backend_card=top.card)`，`card.start_timer()`。保留"only v3"守卫（非 v3 退回 deckbrowser 并告警）。
- **显示问题**：复刻 `_showQuestion` 管线——`q=card.question()`；`prepare_card_text_for_display`（`media.escape_media_filenames` + **`[sound:]`→可点击 replay-button HTML**，发 `play:q:N`）；type-in-answer 过滤；bodyclass（`card cardN` + nightMode）；自定义调度 hook（见下）；**下推 `call _showQuestion(q, a, bodyclass)`**（优先 call，回退 eval）。
- **显示答案**：复刻 `_showAnswer`——`a=card.answer()`；type-ans answer 过滤（`col.compare_answer`）；下推 `_showAnswer(a)`；显示 ease 按钮。
- **底栏按钮**：移植 `_bottomHTML`/`_showAnswerButton`/`_showEaseButtons`/`_answerButtons`/`_remaining`（Edit/More 略或占位；Show Answer→`pycmd("ans")`；ease1-4 按钮，标签 Again/[Hard]/Good/[Easy]，间隔预览来自 `col.sched.describe_next_states(states)`；默认 ease=3；剩余计数）。复用 `reviewer-bottom.js` 的 `showQuestion/showAnswer/selectedAnswerButton`。
- **type-in-answer**：移植 `[[type:Field]]`/`[[type:cloze:Field]]`/`[[type:nc:Field]]`；问题侧注入 `<input id=typeans>`，答案侧 `compare_answer` 上色 diff。回读用 `evalWithCallback("getTypedAnswer();")`。
- **答题流（v3）**：`pycmd("easeN")` → `rating_from_ease` → `col.sched.build_answer(card, states, rating)` → `col.sched.answer_card(answer)`→`OpChanges` → `OpChanges` 广播 + `nextCard()`（无卡则 congrats）。leech 检测 `state_is_leech`。
- **`[sound:]` 音频**：replay-button HTML 已注入；`play:q:N`/`play:a:N` → 服务端取 `card.question_av_tags()/answer_av_tags()` 的第 N 个 → 返回 media 文件 URL → 浏览器 HTML5 `<audio>` 播放（媒体经 §3.2 服务）。autoplay 受 `card.autoplay()` 与浏览器手势策略约束。**TTS/录音暂缓。**
- **自定义调度 (cardStateCustomizer)**：移植 `_run_state_mutation_hook` + `RUN_STATE_MUTATION`：下推 eval `anki.mutateNextCardStates('<key>', async (states,customData,ctx)=>{<user_js>}).finally(()=>bridgeCommand('statesMutated'))`；前端经 `getSchedulingStatesWithContext`/`setSchedulingStates`（§4.3）往返；`statesMutated` 上行解锁 ease 按钮渲染（复刻 `_states_mutated` 门）。配置源 `cardStateCustomizer`（col 配置）。
- **auto-advance**：移植决策逻辑（`secondsToShowQuestion/secondsToShowAnswer/questionAction/answerAction/waitForAudio/stopTimerOnAnswer`，均在 deck 预设里），定时器用浏览器 `setTimeout` 或服务端 asyncio。`Shift+A` 切换。
- **键盘快捷键/右键菜单**：核心（空格=显示答案/默认 ease、1-4=ease、e=编辑[占位到 D]、r=重播）用客户端 keydown→bridge；其余（set-due 对话框、flag/mark、bury/suspend、forget、delete）多属 D，本 spec 占位或最小实现。

### 6.4 Congrats（`screens/congrats`）

- 复用 SvelteKit congrats 路由：服务 `/congrats`（SPA），前端 `+page.ts` 调 `congratsInfo({})`（§4.3）。去掉 Qt 的 `moveToState` 副作用。`unbury`/`customStudy` bridge 链接按需。

### 6.5 Web 外壳与原语（§5 之上，子项目 A 的最小集）

- 极简 **vanilla TS**（esbuild 打包，无 React/Vue，贴近 Anki 的"无前端框架"），源码 `shell_src/`：
  - 页面引导 HTML（注入 i18n 引导 + `#night` + pycmd shim + WS 连接）。
  - 顶栏：Decks / Add / Browse / Stats（**去掉 sync**）；Add/Browse/Stats 在本 spec 为占位导航（落地于 D/E）。
  - 客户端路由：在 deckbrowser/overview/reviewer/congrats 间切换（对应桥接 `moveToState` 语义）。
  - 原语：Web 右键菜单、模态、文本输入框、快捷键注册——供 deckbrowser 齿轮菜单、unbury 模式选择、create deck 输入等使用。

---

## 7. 工程结构与技术栈

- 后端：`FastAPI` + `uvicorn`（单进程）；WebSocket 用 Starlette 内置；protobuf 用 `anki` 自带 `*_pb2`（标准 Python protobuf）。
- 前端：复用 `web_assets/`（vendored）；自研 shell 用 TypeScript + esbuild（轻量、无 SPA 框架、无需 Anki 构建链）。
- 目录（建议）：

```
ankiweb/
  app.py                 # FastAPI 应用装配、生命周期
  config.py              # 路径/端口/collection 位置
  collection_service.py  # §2
  assets.py              # §3 静态服务
  anki_rpc/
    __init__.py          # §4 POST /_anki/{method} 调度
    passthrough.py       # 透传注册表
    handlers.py          # 自定义处理器(congrats/scheduling-states/...)
  bridge/
    ws.py                # §5 WebSocket 端点 + 连接管理
    protocol.py          # 消息类型
    ui_state.py          # per-context UI 状态镜像(为 B 的 gui* 预留)
  screens/
    deckbrowser.py overview.py reviewer.py congrats.py  # §6
    html_gen.py          # 移植的 HTML 生成器
  shell_src/             # 自研 TS(esbuild) -> static/
    bootstrap.ts pycmd_shim.ts router.ts toolbar.ts primitives.ts
  web_assets/            # vendored _aqt/data/web/ (+ VERSION)
  static/                # shell 构建产物
tools/
  fetch_web_assets.py    # §3.1
tests/
docs/superpowers/specs/  # 本 spec
```

---

## 8. 数据流示例

**学一张卡（端到端）**：
1. 浏览器 `/`（shell）→ 路由到 deckbrowser → WS 连接 `ctx=deckbrowser`。
2. deckbrowser handler：`run(col.sched.deck_due_tree)` → 生成 HTML → 渲染。
3. 点牌组 → `pycmd("open:<id>")` → `col.decks.set_current` → 导航 overview。
4. overview：`run(col.sched.counts)` → 渲染；Study Now → `pycmd("study")` → 导航 reviewer。
5. reviewer：`get_queued_cards` → `_showQuestion` push（call）→ 显示问题。
6. 空格 → `pycmd("ans")` → `evalWithCallback(getTypedAnswer)` → `_showAnswer` push + ease 按钮。
7. `pycmd("ease3")` → `build_answer` + `answer_card` → `OpChanges{study_queues}` 广播 → `nextCard` → 下一张或 congrats。

**外部变更刷新**：任一变更操作 → `OpChanges` → `broadcast_opchanges` → 各屏按位失效（deckbrowser 重取 due 计数等），`initiator` 过滤自触发。

---

## 9. 测试策略

- 单元：
  - `collection_service`：单 worker 串行化（并发提交多操作不破坏 Python 端状态）、open/close、OpChanges 投递。
  - `anki_rpc`：透传方法对拍 `mediasrv` 行为（同输入字节→同输出字节）；camel/snake 命名映射边界；响应约定（binary/204/500）。
  - `bridge`：pycmd 往返 + 回调关联、domDone 握手与动作队列缓冲、opchanges 广播与 initiator 过滤、state_mutation_key 校验。
  - `html_gen`：deckbrowser/overview HTML 生成器对拍 Anki 输出（用同一 `DeckTreeNode`/counts 输入）。
- 集成：建临时 collection（用 stdmodels 加一张 Basic 卡）→ deckbrowser 显示计数 → overview → reviewer 显示问题 → 显示答案 → ease3 → 计数刷新。
- 工具：可借用 `anki` 包自带能力创建测试 collection；media/音频用最小样例。

---

## 10. Phase 0 Spike（实现第一步，先于大规模编码）

风险已大幅退除（版本、资源、后端 API 均已验证）。**剩余最高优先验证**：

1. `pip install anki==25.9.4` 在本机 Python 3.12 成功导入 `anki.collection.Collection`，能开/建 collection，`col._backend.<m>_raw(b"")` 可调用，`*_pb2` 可导入。
2. `tools/fetch_web_assets.py` 跑通，`web_assets/` 齐全。
3. **端到端最小验证**：FastAPI 服务 `reviewer.js` + 我们的 WS 桥接 + pycmd shim，用真实卡片让 `_showQuestion(...)` 在浏览器正确渲染、`pycmd("ans")` 回传、`getTypedAnswer` 往返成功。这是验证"①方案的桥接对接真实 bundle"是否成立的关键一跳。

Spike 通过后再展开 §2–§6 全量实现。

---

## 11. 风险与未决项

- **桥接对接真实 bundle 的细节**：`reviewer.js` 期望的全局函数签名/`anki` 全局/`require` 注册（`registerPackage`/runtime-require）必须在我们的 shim 环境里齐备，否则 `_showQuestion` 等找不到。Phase 0 Spike 专门验证。（中风险）
- **`body_classes_for_card_ord` 输出格式**：`.card` CSS 期望的 class（`card cardN nightMode`）需实测确认。（低）
- **`_add_play_buttons` 精确 HTML**：在 `aqt`，实现 replay 按钮时读取确认（发 `play:q:N`）。（低）
- **camel/snake 命名边界**：`i18n` 等缩写，需测试。（低）
- **collection 路径与多标签页**：单用户但浏览器可能开多标签；本 spec 假定单活动会话，多 WS 共享同一 collection（已串行化），UI 状态镜像按 context 维护。（低）

---

## 12. 后续子项目衔接

本 spec 的脊柱（§2–§5）直接支撑：
- **B（AnkiConnect API）**：`/` JSON-RPC（`{action,version,params,key}`、v≤4 裸值/v≥5 信封、`multi`、CORS no-Origin 放行、可选 apiKey），122 个 action（去 sync）映射到 `collection_service` 高层 API / `col.db` SQL；gui* 经 `bridge/ui_state.py` 的状态镜像 + WS 命令。
- **D（Browser + Editor）**：表格虚拟化 + 批量 `browser_row_for_id`（需自加 batch 端点）、侧栏树、搜索、选区动作、查找替换、预览器（复用 reviewer 栈）、card-info（复用 sveltekit）、Add/Edit 宿主（复用 `editor.js`，字段 load/save 桥接协议、媒体粘贴/拖拽走浏览器原生 + FastAPI media 端点）。
- **E（其余界面）**：deck options / graphs / change-notetype / import / custom study / 过滤牌组 / 图像遮挡（多为复用 sveltekit 页 + 自定义处理器重写 Qt 副作用）。
