# THIRD_PARTY_ASSETS — 非代码文件的来源说明

本文件说明仓库中**每一个非代码文件**的来源、生成方式和再分发约束。代码部分的许可见 [LICENSE](LICENSE)（MIT）。

一句话版本：动画画面是为本项目用 Google Gemini 图像模型生成的；语音是脚本纯程序合成的；两者都不含任何来自原作或第三方的素材。

---

## 1. 动画与美术素材（`assets/anims/`、`work/`）

### 生成方式

12 组动画（`idle`、`blink`、`walk`、`sit`、`yawn`、`sleep`、`happy`、`angry`、`surprised`、`eat`、`drag`、`beast`）**全部由 [`tools/gen_art.py`](tools/gen_art.py) 生成**，它通过 **OfoxAI 中继**（`tools/ofox.py`）调用 **Google Gemini 图像模型**，把提示词渲染成图片。

| 项目 | 说明 |
| --- | --- |
| 生成脚本 | `tools/gen_art.py` |
| 中继服务 | OfoxAI（`https://api.ofox.io/v1`），客户端实现见 `tools/ofox.py` |
| 图像模型 | 实际用于出图的是 `google/gemini-3-pro-image`（见 `gen_art.py` 中的 `MODEL` 常量，由 `tools/candidates.py` 的六模型选型结果按目视挑选） |
| 选型过的模型 | `google/gemini-3.1-flash-image`、`google/gemini-3.1-flash-lite-image`、`google/gemini-3-pro-image`、`google/gemini-2.5-flash-image`、`microsoft/mai-image-2.5-pro`、`openai/gpt-image-2` |
| 提示词 | **完整记录在仓库里**，不需要外部资料即可复现 |
| 生成时间 | 2026 年，本项目开发期间 |

### 提示词记录在哪里

`tools/gen_art.py` 里的这几处就是全部提示词来源，逐字可查：

- `CHAR` —— 角色身份锚点：圆滚滚的三花猫，粗黑描边、平涂赛璐璐上色、金色竖瞳、短粗尾巴，并逐条写明「从观众视角看」的三花斑块位置，保证每一帧的花色不会镜像错位。
- `BEAST` —— 巨大白色妖兽形态的外观描述。
- `BG` —— 纯色 `#00FF00` 绿幕背景要求（后续抠像用）。
- `STYLE_TAIL` —— 构图与画幅要求。
- `SHEET_VIEWS` —— 参考视图（front / side / sit / sleep / beast_front / beast_side）。
- `ACTIONS` —— 12 个动作，每个动作 4 帧的逐帧描述。

另外每次生成时脚本会把当时的完整提示词原文写到磁盘上（`work/sheets/<动作>.prompt.txt`、`work/views/<视图>.prompt.txt`、`work/candidates/prompt.txt`），这些文件也随仓库保留，用于核对与复现。

### 中间产物

`work/` 目录里是流水线的中间结果，不参与发布，可以随时删除：

- `work/candidates/` —— 六个模型的风格选型图（`front-<模型名>.png`）与 `contact-sheet.png` 对照表；
- `work/views/` —— 参考视图；
- `work/sheets/` —— 每个动作的 2×2 雪碧图；
- `work/frames/` —— 抠像对齐后的逐帧 RGBA PNG。

### 从雪碧图到 WebM

`tools/build_assets.py` 把一张 2×2 雪碧图切成 4 帧，将平坦的绿幕抠成 alpha，按中位高度统一缩放（目标高 300px），再按姿势族对齐到同一条地平线（`GROUND_Y = 340`），最后用 ffmpeg 的 `libvpx-vp9` 编码成 **带 alpha 平面的 VP9 WebM，画布 360×360**。

### 来源声明

- **没有任何一帧使用原作截图、官方设定图、官方立绘或任何第三方美术素材。** 全部画面都是为本项目生成的。
- 生成过程是「文字描述 → 图像模型」，描述中刻意只使用外观特征（体形、花色位置、瞳色、尾巴形状），**没有要求模型复刻任何具名角色的原画**。
- `assets/anims/` 下的 WebM 与 `work/` 下的 PNG 属于**本项目的美术产出**，不在 MIT 许可范围内，见 [LICENSE](LICENSE) 的「Media assets」一节。
- 角色本身是《夏目友人帐》的**非官方粉丝向再创作**，与原作权利方无隶属关系。

---

## 2. 占位语音（`assets/voice/`）

### 生成方式

`assets/voice/` 下的 7 个 WAV 文件**全部由 [`tools/gen_voice.py`](tools/gen_voice.py) 程序化合成**，不含任何录音、采样或第三方音频。

| 文件 | clip id | 合成配方（脚本内 `CLIPS` 表） |
| --- | --- | --- |
| `natsume.wav` | `natsume` | 单声喵叫：基频 430→700→330 Hz，0.72 秒 |
| `happy.wav` | `happy` | 更亮的喵叫：500→820→420 Hz，0.52 秒 |
| `angry.wav` | `angry` | 短促的恼怒叫声，0.34 秒 |
| `surprised.wav` | `surprised` | 高而尖的短喵：620→980→520 Hz，0.34 秒 |
| `eat.wav` | `eat` | 240 Hz 颤音，0.85 秒 |
| `purr.wav` | `purr` | 180 Hz 呼噜颤音，1.4 秒 |
| `sleep.wav` | `sleep` | 150 Hz 低沉呼噜，1.8 秒 |

合成方式是声门脉冲串（glottal pulse train）+ 双共振峰（formant）滤波 + 幅度包络 + 少量呼吸噪声，44.1 kHz / 16-bit / 单声道。脚本注释里写得很清楚：它**刻意做得卡通化、不像真人**，以免被误认为角色原声。复现只需：

```bash
python tools/gen_voice.py
```

### 它们不是什么

**它们不是动画原声，也不是任何真人配音的复制或近似模仿。** 原版动画中该角色的台词是受版权保护的商业录音，本项目没有权利分发，因此只提供能跑通播放链路的合成占位音。

---

## 3. 如果你替换了语音

这一节写给**想要分发本插件（或其副本）的人**。

插件的设计允许用户把自己的音频丢进用户目录：

```
%USERPROFILE%\.dsh\dsh-nyanko-sensei\voice\<语音包>\<clip id>.<扩展名>
```

用户根优先于包内资源，所以放一个 `natsume.mp3` 就能覆盖自带的占位音。**这是给你自己听的。**

一旦你把**商业录音**（动画原声、影视片段、商业唱片、付费语音库、任何你并不持有权利的音频）放进语音包目录，那份文件就不再是「本项目的美术产出」，而是**受版权保护的第三方录音**。此时：

- **不要**把该文件提交到任何公开仓库；
- **不要**把包含该文件的目录打包后发布、上传网盘、发到群里或分发给任何人；
- **不要**在 npm / GitHub Release / 任何分发渠道的产物里包含它；
- 只在你自己的机器上留作个人使用。

也就是说：**含商业录音的副本不可公开**。你要发布的是「插件 + 合成占位音」，让使用者自己按 [README 的语音一节](README.md#语音) 去补他们自己的音频。这是插件自带合成占位音而不是自带原声的唯一原因。

同理，如果你基于本项目的图像模型与提示词**更换或重新生成**了美术素材，请自行确认新素材的来源与授权，并在这里补充说明。

---

## 4. 汇总表

| 路径 | 类型 | 来源 | 是否含第三方素材 | 许可 |
| --- | --- | --- | --- | --- |
| `lib/`、`tools/` | 源码 | 本项目作者 | 否 | MIT（见 [LICENSE](LICENSE)） |
| `assets/anims/*.webm` | 动画 | Google Gemini 图像模型经 OfoxAI 生成，`tools/gen_art.py` | 否 | 不属 MIT，随插件使用 |
| `work/**` | 中间产物 | 同上 | 否 | 不属 MIT，可删除 |
| `docs/preview/*.gif` | 预览图 | 由 `assets/anims/` 的帧合成，`tools/build_assets.py` | 否 | 同 `assets/anims/` |
| `assets/voice/*.wav` | 占位音频 | 纯程序合成，`tools/gen_voice.py` | 否 | 不属 MIT，随插件使用 |
| 用户语音包 | 音频 | **使用者自己提供** | **可能是** | 由使用者自行负责，见第 3 节 |
