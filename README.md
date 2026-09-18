<div align="center">

# dsh-nyanko-sensei · 娘口三三

**住在 DeepSeek Harness Web 界面里的圆滚滚三花猫桌宠。**

[![npm](https://img.shields.io/badge/install-github%3AQihang--He%2Fdsh--nyanko--sensei-2f6fed?style=flat-square)](https://github.com/Qihang-He/dsh-nyanko-sensei)
[![GitHub](https://img.shields.io/badge/GitHub-Qihang--He%2Fdsh--nyanko--sensei-181717?style=flat-square&logo=github)](https://github.com/Qihang-He/dsh-nyanko-sensei)
[![License](https://img.shields.io/badge/license-MIT-3da639?style=flat-square)](LICENSE)
[![DeepSeek Harness](https://img.shields.io/badge/DeepSeek%20Harness-plugin-4d6bfe?style=flat-square)](https://github.com/deepseek-ai)
[![Web profile](https://img.shields.io/badge/profile-web-8957e5?style=flat-square)](#安装)

</div>

---

娘口三三是《夏目友人帐》里那只圆得像团子的三花猫老师。这个插件把它请进 DSH 的 Web 界面：它蹲在屏幕角落自己发呆、打哈欠、睡一会儿、到处溜达，你点它一下它会不高兴或者很得意地叫一声，你把它拎起来甩出去它会撞墙弹回来，你干活的时候它跟着你的进度换表情。

纯前端桌宠，**不改动 DSH 的任何 DOM 结构**，不占用任何 UI 插槽，卸载后界面上不留痕迹。

## 功能预览

> **这个仓库里没有图片。** 动图与截图都是角色画面，而角色画面派生于使用者自己提供的
> 美术素材，带有与素材相同的再分发限制，因此不随仓库分发。下面的路径在本地构建后
> 就会出现，构建步骤见[开发](#开发)。

在真实页面里的样子（截图由 [`tools/verify-browser.mjs`](tools/verify-browser.mjs) 的端到端验证自动产出，不是手工摆拍，因此永远和当前代码一致）：

```
docs/screenshot.png
```

13 个动作的循环预览由构建逐动作写出（`tools/gen_motion.py` 生成）：

| 类别 | 动作 |
| --- | --- |
| 待机循环 | `idle` 呼吸、`breathe_deep` 深呼吸、`look_around` 张望、`sleep` 打盹 |
| 移动 | `walk` 走路 |
| 小动作 | `ear_flick` 抖耳 |
| 反应 | `hop` 跳、`bounce_land` 落地压弹、`happy` 高兴、`angry` 生气、`surprised` 吃惊、`spin` 转圈 |
| 拖拽 | `drag` 悬空挣扎 |

预览图路径为 `docs/preview/<动作名>.gif`。构建命令：

```bash
python tools/gen_motion.py        # 需要 work/sprites/base.png
python tools/motion_sheet.py      # 逐帧审阅图，判断动作好坏看这个
```

> 动作资源的构建是增量的：`assets/anims/` 里缺哪个动作，客户端就会跳过它并退回 `idle`，桌宠本身照常可用。

**两个方向的构建路径**，按手上有没有出图凭据选：

| | 需要出图 key | 还原度 | 动作生动度 |
| --- | --- | --- | --- |
| `tools/gen_art.py` 出图 → `build_assets.py` 合成 | 是 | 近似（照文字描述重画） | 高，可多姿势 |
| `tools/gen_motion.py` 形变已有美术 | 否 | **精确**（像素就是原画） | 中，单姿势 |

见 [`STATUS.md`](STATUS.md) 了解两条路各自的取舍与实测结论。

## 安装

插件以 npm 包的形态发布在 GitHub 上，通过 DSH 的插件管理命令装进 `web` profile。

### 从 GitHub 安装（推荐）

```bash
dsh plugin --profile web add github:Qihang-He/dsh-nyanko-sensei
dsh web
```

第二条命令是必要的：插件行与浏览器端的 bundle 在进程启动时装载，装完必须重启 `dsh web` 才会生效（刷新浏览器页面不够）。

### 从源码安装（本地路径）

```bash
git clone https://github.com/Qihang-He/dsh-nyanko-sensei.git
cd dsh-nyanko-sensei
dsh plugin --profile web add .
dsh web
```

`add .` 装的是当前目录——请先 `cd` 进 `package.json` 所在的仓库根目录再执行，否则 pnpm 会去找别的包。

### 更新

```bash
dsh plugin --profile web add github:Qihang-He/dsh-nyanko-sensei
dsh web
```

GitHub 来源的依赖按 commit 解析，重新执行 `add` 即可拉到最新版本。源码安装则在该仓库里 `git pull` 后重启 `dsh web`。

### 卸载

```bash
dsh plugin --profile web remove dsh-nyanko-sensei
dsh web
```

设置不会被清除。如果想一并删掉，在浏览器控制台执行 `localStorage.removeItem("dsh-nyanko-sensei:settings")`；自己录的语音文件在用户目录里（见[语音](#语音)），需要手动删除。

### ⚠️ 只保留一种安装来源

同一个插件**不要同时从 GitHub 和本地路径安装两次**。两条记录都写进 `web` profile 的依赖里时，插件行会出现两次，DSH 启动阶段解析到重复条目会直接失败，服务起不来。

补救办法是回到单来源状态：

```bash
dsh plugin --profile web remove dsh-nyanko-sensei
dsh plugin --profile web add github:Qihang-He/dsh-nyanko-sensei
dsh web
```

## 如何使用

装载完成后，娘口三三出现在视口右下角（默认 180px，可在设置里改）。

| 操作 | 效果 | 对应实现 |
| --- | --- | --- |
| **左键单击** | 随机播放 `happy` / `angry` / `surprised` / `eat` / `beast` 之一并说一句台词，同时标记为「已选中」（出现虚线圈） | [`lib/client.js`](lib/client.js) `clickReaction()` |
| **点头部**（上方 42% 区域） | 额外有 50% 概率冒出开心的吐槽 | 同上，`region === "head"` |
| **点尾巴**（右侧 32% 区域） | 额外有 50% 概率冒出骂人的话 | 同上，`region === "tail"` |
| **按住拖动** | 播放 `drag`（四条腿下垂挣扎）；松手若移动超过 4px 视为拖拽，不触发点击 | `bindGlobal()` / `pointermove` |
| **快速甩出** | 带着惯性飞出去，撞到屏幕四边按 0.55 的恢复系数弹回，落地后变回 `happy` | `step()` 中的惯性段 |
| **单击选中 → 点击别处** | 猫走到你点的位置，中途播放 `walk`，朝向自动翻转 | `startWalkTo()` |
| **右键** | 打开快捷菜单（项见下表） | `openMenu()` |
| **听它自言自语** | 按活跃度档位随机冒气泡，台词从 `LINES` 表里挑 | `autonomyStep()` |
| **自己溜达** | 空闲计时器到点后按概率随机换位置 | `scheduleAutonomy()` |
| **窗口缩放** | 位置自动夹回可视区域内，不会卡在屏幕外 | `window` 的 `resize` 监听 |
| **跟随 Agent 状态** | 侦测到「生成中 / 等待批准 / 出错 / 完成」时切换动作与台词 | `watchAgent()` / `detectBusy()` |
| **系统「减弱动态效果」** | 关闭交叉淡入淡出与走路上下颠簸 | `reducedMotion()` |

### 右键快捷菜单

| 菜单项 | 行为 |
| --- | --- |
| 呼唤「なつめ」 | 播放点击台词音频（默认 clip `natsume`）+ `happy` + 气泡「なつめ！」；音频不存在时该项置灰 |
| 摸摸头 | 播放 `happy` |
| 变身 | 播放 `beast`（巨大的白色妖狐真身）并说一句「退下！」 |
| 睡一会儿 | 强制切到 `sleep` |
| 散步 | 随机挑一个 x 坐标走过去 |
| 大小 NNNpx ( + / − ) | 每次点击增大 20px（80–420 区间内循环夹取） |
| 显示 / 隐藏 | 切换桌宠可见性，写入设置 |
| 回到初始位置 | 速度清零，回到设置里的角落 |
| 打开完整设置… | 打开右侧设置面板 |

> 「大小」这一项每次点击 +20px，超过上限后再点仍停在上限；想精确调节请用设置面板里的滑杆。

## 功能说明

### 动画状态机

`lib/client.js` 的 `ANIMS` 表定义了 12 个动作，格式统一为 **VP9 带 Alpha 通道的 WebM，画布 360×360**。下表是客户端声明的完整清单；其中 `idle`、`walk`、`sit` 三个目前已有资源文件，其余动作的提示词齐备但资源尚未构建，客户端会把缺失的动作跳过并退回 `idle`（见[功能预览](#功能预览)）：

| 动作 | 类型 | 时长 | 说明 |
| --- | --- | --- | --- |
| `idle` | 循环 | — | 站立、呼吸 |
| `blink` | 单次 | 420ms | 眨眼，结束回 `idle` |
| `walk` | 循环 | — | 迈步，移动时使用 |
| `sit` | 循环 | — | 端坐 |
| `yawn` | 单次 | 1400ms | 打哈欠，结束回 `idle` |
| `sleep` | 循环 | — | 蜷成一团睡觉 |
| `happy` | 单次 | 1200ms | 开心跳跃，结束回 `idle` |
| `angry` | 单次 | 1200ms | 炸毛，结束回 `idle` |
| `surprised` | 单次 | 1000ms | 受惊，撞墙时也会放 |
| `eat` | 单次 | 1600ms | 吃团子 |
| `drag` | 循环 | — | 被拎起来四肢乱蹬 |
| `beast` | 单次 | 2000ms | 变身巨大白兽 |

单次动作结束后回到 `idle`。实现上有三道保险：`ended` 事件、`busyUntil` 超时兜底、以及 `step()` 里的一次轮询，所以即使某个视频没能正常结束事件也不会把猫卡在最后一帧。

渲染用**两个 `<video>` 元素双缓冲**：切动作是交叉淡入淡出，不会闪一帧空白。`assets/anims/` 里缺哪个文件，该动作就会被跳过、退回 `idle`，猫仍然可用。

### 与 Agent 活动联动

娘口三三会**观察对话区域的 DOM 变化**（`MutationObserver` 挂在 `document.querySelector("main")`，退化到 `document.body`）来猜你现在的状态。这是一个**启发式判断，不是 RPC 订阅**：

- 它有 900ms 的防抖，流式输出的密集更新不会把它打爆；
- 状态要连续稳定 1200ms 才会被采纳（迟滞），避免抖动；
- 判断依据是最多 4000 字符的正文文本，用几组关键词匹配：`停止 / Stop` → 生成中，`允许 / 拒绝 / Approve / Deny / 等待批准` → 等你确认，`出错 / 失败 / Error / Failed` → 出错，`完成 / Done / Finished` → 干完了。

映射出来的反应：

| 侦测状态 | 动作 | 台词（带概率） |
| --- | --- | --- |
| 生成中 | `walk` | `work` 18% |
| 等你确认 | `sit` | `waiting` 30% |
| 出错 | `surprised` | `fail` 70% |
| 完成 | `happy` | `done` 60% |

它选择了监听 DOM 而不是订阅宿主事件，是因为这样**不需要任何宿主 API、不依赖 GUI 内部结构、坏了也只是「收不到信号」而不会报错**——收不到信号时它就退回全自主行为。可以在设置里用「跟随 Agent 状态」关掉。

### 自主行为与活跃度

空闲计时器在 `ACTIVITY` 表里定义了三档，设置面板里对应「活跃度」：

| 档位 | 空闲间隔 | 溜达概率 | 自言自语概率 |
| --- | --- | --- | --- |
| `quiet` 安静 | 14–30 秒 | 12% | 0% |
| `balanced` 均衡（默认） | 7–16 秒 | 30% | 5% |
| `lively` 活泼 | 3.5–8 秒 | 50% | 14% |

到点后依次判断：先掷骰子决定要不要溜达，其次掷骰子决定要不要冒一句话配一个 `happy` / `angry` / `surprised`，都没有就换一个休息姿势。休息姿势从 `idle`（权重 3 倍）、`sit`、`blink`、`sleep`、`yawn`、`walk` 的池子里抽。拖动中、菜单打开中、设置面板打开中都会跳过自主行为。

### 气泡台词

打开「气泡台词」后，`LINES` 表里的中文台词会在猫头顶的气泡里显示 `bubbleMs` 毫秒（默认 4200ms）。台词按情绪分组：`greet`、`happy`、`angry`、`sleepy`、`work`、`done`、`fail`、`waiting`、`beast`。气泡用 DSH 的主题变量着色，自动跟随浅色/深色主题。

### 减弱动态效果

系统开启了 `prefers-reduced-motion: reduce` 时：

- 切动作的交叉淡入淡出被关掉，直接换帧；
- 走路时的上下颠簸被去掉，只有平移；
- 甩出去的惯性弹跳被禁用，松手直接落地。

该偏好是**实时采样**的，你在系统设置里改完不需要重载页面。

## 设置

设置存在 `localStorage` 的 `dsh-nyanko-sensei:settings` 键下，**全部通过宠物自己的界面修改**（右键 → 打开完整设置…），DSH 的设置面板里没有对应卡片。

| 字段 | 含义 | 默认值 |
| --- | --- | --- |
| `visible` | 是否显示桌宠 | `true` |
| `size` | 桌宠边长（px），面板滑杆范围 80–420 | `180` |
| `corner` | 初始停靠的角落：`bottom-right` / `bottom-left` / `top-right` / `top-left` | `"bottom-right"` |
| `marginX` | 初始停靠时距左右边缘的距离（px） | `28` |
| `marginY` | 初始停靠时距上下边缘的距离（px） | `28` |
| `speed` | 移动速度参数（当前版本尚未接线，见下方说明） | `60` |
| `activity` | 活跃度：`quiet` / `balanced` / `lively` | `"balanced"` |
| `voiceEnabled` | 是否播放语音 | `true` |
| `voiceVolume` | 音量，面板滑杆 0–100 映射到 0–1 | `0.9` |
| `voicePack` | 使用哪个语音包目录名 | `"default"` |
| `clickVoice` | 点击时优先播放的 clip id | `"natsume"` |
| `bubbles` | 是否显示气泡台词 | `true` |
| `bubbleMs` | 气泡停留时间（ms） | `4200` |
| `reactToAgent` | 是否跟随 Agent 状态 | `true` |
| `wander` | 是否允许自主漫游 | `true` |
| `showSettingsHint` | 设置面板提示文案的开关（当前版本尚未接线，见下方说明） | `true` |

> `corner`、`marginX`、`marginY` 只在页面加载和「回到初始位置」时生效；平时猫停在你上次把它放在的地方。
> `speed` 与 `showSettingsHint` 是当前版本尚未接线的预留字段：它们会被持久化，但设置面板里没有对应控件，改它们不会改变现在的行为。

设置面板底部有「恢复默认设置」，会把上面整张表恢复成默认值。

## 语音

**这一节请仔细读——插件不附带任何原版动画语音。**

### 点击时发生了什么

点击桌宠时，宠物会尝试播放 clip id 为 **`natsume`** 的音频（由 `DEFAULTS.clickVoice` 指定，可在设置面板里改成别的 clip id）。

如果这个音频不存在，什么都不会发生——不报错、不弹窗，只是安静地切动作。右键菜单里的「呼唤「なつめ」」在这一情况下会是灰色不可点。

### 仓库里只有合成占位音

`assets/voice/` 下确实有 7 个 MP3 文件（`natsume`、`happy`、`angry`、`surprised`、`eat`、`purr`、`sleep`），它们**全部由 [`tools/gen_voice.py`](tools/gen_voice.py) 程序化合成**：声门脉冲串 + 共振峰 + 包络 + 一点呼吸噪声，是一只卡通猫式的「喵」，刻意做得不像真人配音。

**它们不是动画原声，也不可能是**——原版配音是商业录音，本插件无权分发，所以只提供能跑通播放链路的占位文件。

### 换成你自己的音频

宿主端从两个根目录提供媒体文件，**用户根优先于包内资源**，所以放一个同名文件就能覆盖，不需要重新构建、不需要改包内任何文件：

```
<用户根>\voice\<语音包名>\<clip id>.<扩展名>
```

Windows 上默认 `DSH_HOME` 是 `%USERPROFILE%\.dsh`，因此最常见的样子是：

```
%USERPROFILE%\.dsh\dsh-nyanko-sensei\voice\custom\natsume.mp3
```

- **`voice\` 根目录下的文件**属于名为 `default` 的语音包；
- **`voice\<子目录>\` 里的文件**构成一个以该子目录命名的语音包，在上面的例子里语音包叫 `custom`，在设置面板的「语音包」下拉框里选中它即可；
- 文件名（去掉扩展名）就是 **clip id**，`natsume.mp3` 的 clip id 是 `natsume`；
- 放了音频后**刷新浏览器页面**即可生效，不需要重启 `dsh web`（宿主端每次请求都重新读盘，manifest 也标了 `no-store`）。

支持的扩展名：`mp3`、`m4a`、`aac`、`ogg`、`oga`、`opus`、`wav`、`flac`。同名文件存在多个格式时，按上面这个顺序取第一个。

已识别的 clip id：`natsume`、`happy`、`angry`、`surprised`、`eat`、`purr`、`sleep`。其中 `happy` 动作自带 `["natsume", "happy"]` 两条语音，其余动作只会念自己的 id。

### 用麦克风录一条

[`tools/record-voice.ps1`](tools/record-voice.ps1) 会从麦克风录一段、掐掉前后静音、做响度归一化，然后直接写进用户语音包。

先列出 ffmpeg 能看到的录音设备：

```powershell
pwsh -File tools/record-voice.ps1 -ListDevices
```

只找到一个设备时会自动选中，直接录：

```powershell
pwsh -File tools/record-voice.ps1 -Seconds 6
```

多个设备时用 `-Device` 指定（名字照抄列表里的输出）：

```powershell
pwsh -File tools/record-voice.ps1 -Device "Microphone (Realtek(R) Audio)" -Seconds 6 -Clip natsume -Pack custom
```

有 3 秒准备时间，按 Enter 可以提前停止。产物写到 `%USERPROFILE%\.dsh\dsh-nyanko-sensei\voice\custom\natsume.mp3`。参数：`-Clip`（默认 `natsume`）、`-Seconds`（默认 8）、`-Device`、`-Pack`（默认 `custom`）。脚本需要 ffmpeg 在 PATH 上。

npm 脚本里也有一条等价入口：

```bash
npm run voice:record
```

### ⚠️ 音频责任

**你自己放进语音包里的音频由你自己负责。** 如果你从动画原声里截取、或从任何商业唱片、影视作品里提取了片段，那是受版权保护的录音：请只在自己机器上做个人用途使用，**不要把该文件随插件一起发布、提交到仓库或通过任何渠道再分发**。插件作者没有、也不会分发这类音频。

## 资源来源与许可

这个项目里有三种性质完全不同的东西，请分别看待：

- **代码**——[`lib/index.js`](lib/index.js)、[`lib/client.js`](lib/client.js)、[`tools/`](tools) 下的脚本，采用 MIT 许可，见 [LICENSE](LICENSE)。
- **美术素材**——`assets/anims/` 里的动画帧，由 [`tools/gen_art.py`](tools/gen_art.py) 通过 OfoxAI 中继调用 Google Gemini 图像模型生成，提示词原文记录在脚本里（`CHAR`、`BEAST`、`ACTIONS` 表），中间产物在 `work/` 目录。**所有画面都是为这个项目生成的，没有使用任何原作截图或官方素材。**
- **语音**——`assets/voice/` 下的占位音由 [`tools/gen_voice.py`](tools/gen_voice.py) 纯程序合成，不含任何第三方录音。

**娘口三三 / 猫咪老师 / ニャンコ先生 是《夏目友人帐》的角色，本项目是粉丝性质的非官方作品，与原作的著作权人、发行方没有任何隶属关系，也未获得其授权或背书。** 角色形象属于原作者与相关权利方。如果你是在原作的著作权人，并对本仓库中的 AI 生成形象有异议，请提 issue，我们会处理。

非代码文件的完整来源说明见 [THIRD_PARTY_ASSETS.md](THIRD_PARTY_ASSETS.md)。

## 开发

### 资源流水线

所有美术和语音资源都是脚本产物，顺序如下：

```bash
# 0. （可选）先做风格选型：同一段角色描述喂给 6 个图像模型，结果落在 work/candidates/
python tools/candidates.py

# 1. 参考视图与动作表：每个动作一张 2x2 雪碧图，落在 work/views、work/sheets
python tools/gen_art.py sheet
python tools/gen_art.py actions          # 也可以只做几个：python tools/gen_art.py actions idle walk

# 2. 抠像、对齐、编码 WebM、生成预览 GIF
python tools/build_assets.py all         # 或 frames / encode / preview 单步跑

# 3. 静态自检：客户端 bundle 能否解析、manifest 指向的文件是否存在、
#    客户端声明的每个动作是否都有对应资源、宿主端能否 import
node tools/check-package.mjs
```

`tools/build-all.cmd` 把上面除选型之外的全部步骤串了一遍，Windows 上双击即可。

npm 脚本是更短的别名：

| 命令 | 等价于 |
| --- | --- |
| `npm run art:views` | `python tools/gen_art.py sheet` |
| `npm run art:actions` | `python tools/gen_art.py actions` |
| `npm run art:build` | `python tools/build_assets.py all` |
| `npm run voice:record` | `pwsh -File tools/record-voice.ps1` |
| `npm run check` | `node tools/check-package.mjs` |

### 图像阶段需要 OfoxAI 凭据

`gen_art.py` 和 `candidates.py` 会真的调用图像生成接口，因此需要一个 **OfoxAI API key**。

`tools/ofox.py` 不从环境变量、命令行或配置文件里读这个密钥，而是**从 DSH 的凭据库读取**：`$DSH_HOME/.credentials.yaml`（Windows 默认 `%USERPROFILE%\.dsh\.credentials.yaml`）里的 `refs.OFOX_API_KEY` 字段。密钥因此不会被写进任何文件、命令行或日志。

```yaml
refs:
  OFOX_API_KEY: "你的密钥"
```

缺少 key 时脚本会直接退出并打印凭据库路径。像素阶段的 `build_assets.py` 是本地的（Pillow + numpy + ffmpeg），不需要网络也不需要 key；ffmpeg 需要能在 PATH 上找到，或在 `D:\ffmpeg-*\bin\ffmpeg.exe` 下。

### 环境要求

- **Node.js** `^22.19.0 || >=24.0.0`（见 `package.json` 的 `engines`）
- **Python 3.10+**，仅资源流水线需要：`numpy`、`Pillow`、`requests`、`PyYAML`
- **ffmpeg / ffprobe**，仅编码与录音需要

浏览器端没有构建步骤——[`lib/client.js`](lib/client.js) 是手写的 `__ModuleLoader__` bundle，纯 DOM 无框架，这样它可被单文件审阅，也不会因为 GUI 的 React 树改结构而失效。

## 目录结构

```
dsh-nyanko-sensei/
├── package.json               # 包清单：exports、dsh.bundle.patch、dsh.client
├── cordis.patch.yml           # bundle 补丁层：往 web profile 里插一行插件
├── lib/
│   ├── index.js               # 宿主端：媒体路由 + manifest（需要 webServer 服务）
│   └── client.js              # 浏览器端：桌宠本体（动画机、交互、语音、自主行为）
├── assets/
│   ├── anims/                 # 动作资源：VP9-alpha WebM（360x360），由流水线生成
│   └── voice/                 # 7 个合成占位 MP3，用户可用自己的音频覆盖
├── tools/
│   ├── ofox.py                # OfoxAI 中继客户端，密钥取自 DSH 凭据库
│   ├── candidates.py          # 多模型风格选型
│   ├── gen_art.py             # 第 1 阶段：提示词 → 2x2 动作雪碧图
│   ├── build_assets.py        # 第 2 阶段：抠像对齐 → 帧 → WebM → 预览 GIF
│   ├── gen_voice.py           # 合成占位语音
│   ├── record-voice.ps1       # 麦克风录音 + 修剪 + 归一化
│   ├── check-package.mjs      # 静态自检：bundle 能否解析、资源是否齐全
│   ├── verify-browser.mjs     # 端到端验证：用 CDP 驱动 Edge 实测桌宠
│   └── build-all.cmd          # 一把梭跑完整条流水线
├── docs/
│   ├── screenshot.png         # 运行时截图（由 verify-browser.mjs 自动产出）
│   └── preview/               # 预览 GIF 输出目录（由 art:build 生成）
├── work/                      # 中间产物（雪碧图、帧、选型结果），可随时删除
├── README.md                  # 中文说明（本文件）
├── README.en.md               # English README
├── LICENSE                    # MIT + 媒体资源说明
└── THIRD_PARTY_ASSETS.md      # 非代码文件的来源与再分发约束
```

用户侧的文件都在 DSH 家里，不在包内：

```
%USERPROFILE%\.dsh\dsh-nyanko-sensei\voice\<语音包>\<clip id>.<扩展名>
```

## 常见问题

**装完看不到宠物**

1. 确认执行过 `dsh web` 重启——插件行是进程启动时装载的，只刷新页面不够。
2. 打开浏览器控制台，找 `[dsh-nyanko-sensei]` 开头的日志。没有 `pet awake at ...` 说明浏览器端 bundle 没被加载。
3. 检查是不是被自己隐藏了：右键点击宠物原本所在的位置，或清掉 `localStorage` 里的 `dsh-nyanko-sensei:settings` 后刷新。
4. 宠物容器是个 `position: fixed` 的全屏覆盖层，`z-index` 为 2147483000。如果页面里挂着更高层级的浮层，猫会被压在下面。

**点击没声音**

这是**预期行为**，不是 bug——插件只带合成占位音，不含原版配音。

1. 先确认设置面板里「启用语音」是开的、音量不是 0。
2. 打开设置面板，看底部提示：它会列出当前发现的语音包和 clip 数量。只要包里自带的 `assets/voice/*.mp3` 被识别到，这里至少会显示 `default(7)`。如果显示「未发现任何语音文件」，说明宿主端的媒体根没有读到包内资源，检查插件是否装全了。
3. 按[语音](#语音)一节把 `natsume.mp3` 放到 `%USERPROFILE%\.dsh\dsh-nyanko-sensei\voice\` 下，然后刷新页面。
4. 浏览器的自动播放策略会拦截没有用户交互的音频播放——点击本身是用户交互，正常不受影响，但如果整页刚加载你就用脚本触发点击，可能被拦。控制台会有相应提示。
5. 右键菜单里「呼唤「なつめ」」是灰的，同样表示 `natsume` 这个 clip 没找到。

**有些动作看不到**

`assets/anims/` 目前只构建了 `idle`、`walk`、`sit` 三个动作（见[功能预览](#功能预览)）。其余 9 个动作的提示词已经写在 [`tools/gen_art.py`](tools/gen_art.py) 里，但资源还没生成——客户端发现文件不存在时会跳过它并退回 `idle`，所以你不会看到报错，只是猫的动作变少了。补齐方式：

```bash
python tools/gen_art.py actions
python tools/build_assets.py all
```

**宠物跑到屏幕外了**

正常拖拽时横向允许超出约 30% 的身位，纵向不允许超出。松手后惯性会把它推回边界内并弹一下。

如果它彻底不见了：

1. 缩放一下窗口——`resize` 监听会把位置夹回可视区域。
2. 右键点击屏幕角落碰运气，或者直接在浏览器控制台执行：
   ```js
   localStorage.removeItem("dsh-nyanko-sensei:settings")
   ```
   然后刷新页面，它会回到默认的右下角。

**动画不透明／有黑底（Safari）**

动画资源是 **VP9 编码、Alpha 通道存在独立平面里的 WebM**。Safari 至今不能解码 VP9 的 alpha 平面，结果就是视频能播但透明通道丢失——猫成了一个带黑底或绿底的方块。

这不是播放逻辑的问题，是编解码器的能力边界。可行的做法：

- 用 Chrome / Edge / Firefox 打开 DSH 的 Web 界面；
- 或者把 `assets/anims/*.webm` 换成带 alpha 的 HEVC/MP4（`lib/client.js` 的 `animUrl()` 目前固定请求 `.webm`，需要相应改一行）。

**宠物消失了但设置还在**

设置存在 `localStorage`，卸载插件不会清除它。重新装回来后，大小、位置、语音包等会沿用上次的值。

---

<div align="center">

本项目与 DeepSeek 官方无隶属关系，是面向 DeepSeek Harness 的社区开源插件。

</div>
