# 交接报告 / Handover

写于我自主工作结束时。你明天回来照这份文档就能接手。

> **本机已按你的要求关机。** 开机后照常启动 DSH 即可（`dsh web`，或用桌面上的 `start-dsh.ps1`）。插件已经在 web profile 里装好了，不需要重装。
>
> 关机前的最后状态：静态自检通过，浏览器端到端验证 **11/11 通过**，13 个动作素材齐全，语音播放正常。

---

## 一、一句话结论

**桌宠已经能用了，11/11 端到端验证通过，装在你的 DSH 里。**
但**"完全真实"这个目标我没有达到**，原因不在实现，在素材来源——下面第三节说清了为什么，以及三条路的实测结果。

---

## 二、现状：能用，且验证过

刷新浏览器页面（Ctrl+F5），右下角就是它。也可以看 `work/shots/desktop-pet.png`。

### 交付物

| 位置 | 内容 |
| --- | --- |
| `D:\Deepseek_Harness\dsh-nyanko-sensei\` | 插件本体（已装进 web profile） |
| `...\dsh-nyanko-sensei-backup-20260918-1908\` | 开工前的完整备份，出事了从这里恢复 |
| `D:\Deepseek_Harness\.dsh-last-url.txt` | DSH 的访问地址（带 token） |
| `work\motion-review\*.png` | **13 个动作的逐帧审阅图**，判断动作好坏看这个 |
| `docs\preview\*.gif` | 13 个动作的循环预览 |
| `docs\screenshot.png` | 运行时截图 |
| `tools\STATUS.md` 同目录的其他 md | 设计与踩坑记录 |

### 13 个动作

都是**程序化形变**做出来的（不是 AI 生成）：`idle`、`breathe_deep`、`look_around`、`walk`、`sleep`、`ear_flick`、`hop`、`bounce_land`、`happy`、`angry`、`surprised`、`spin`、`drag`。

每个 12 帧、384×384、VP9-alpha，全套 831 KiB。

### 交互

点击（触发反应动作 + 播放语音）、拖拽甩抛、撞边反弹、右键菜单、自动漫游、气泡台词、跟随 Agent 状态、`prefers-reduced-motion`。

### 验证

```powershell
cd D:\Deepseek_Harness\dsh-nyanko-sensei
node tools/check-package.mjs          # 静态自检
node tools/verify-browser.mjs         # 端到端：真开 Edge 实测，11/11
```

`verify-browser.mjs` 会自己开一个 headless Edge、加载真实页面、断言 11 项（覆层挂载 / 13 个视频都能加载 / 帧尺寸一致 / 解码播放 / **浏览器实测 alpha 平面存活** / 点击有反应 / 语音 clip 真能解码 / 不会卡在一次性动作 / 双缓冲不变量 / 控制台干净），并顺手产出 `docs/screenshot.png`。**它不需要你在场。**

---

## 三、没达到"完全真实"，以及为什么

### 三条路我都实测了，全部不通

| 路线 | 实测结果 |
| --- | --- |
| **AI 出图**（Google AI Studio） | 需要 key。你手机上不了外网，我无法替你注册（要手机验证码 + 过风控，而且我不该拿你身份注册）。**这条是所有路线里唯一能真正做出"照描述重画的高保真形象"的，但我拿不到 key。** |
| **AI 出图**（OfoxAI，原有 key） | 余额触底（现为 **−$0.20**），文本和图像都 402。 |
| **AI 出图**（Pollinations，免 key） | 通了，但**没有风格控制**：出的是写实猫、橘猫灰猫白猫各画各的、带水印。做不了需要 40+ 帧严格一致的素材。 |
| **网上搜图** | 子代理下了 **529 张**，我写指纹筛选器排出前 32 张看了：**没有一张是动画原画**，全是扭蛋玩具实拍、商品图、通用白橘猫贴纸，还有一堆是**柴犬**（白+橘+灰，指纹确实像）。源本身不对。 |
| **从你的参考图抠像** | 七种算法全部失败，第五节记录了根因——**原理上做不到**。 |
| **程序化形变（最终采用）** | ✅ 可行。以你给的金背景全身图为唯一素材，形变出 13 个动作。**还原度 = 100%（像素就是原画本身）**，代价是单姿势，腿不能独立动。 |

### 还原度现状（诚实版）

- **画面对不对**：✅ 对。用的就是你那张金背景全身图本身——额头橘/白缝/灰三段、项圈金铃铛、短尾、粉肉垫全都在。
- **动作生动度**：⚠️ 一般。单张素材只能做整体挤压拉伸、重心倾斜、头部旋转、耳朵抖动。**走路时腿不会交替**，这是原理限制不是调参问题。
- **语音**：⚠️ **不是动漫原声**。我搜了 6 组关键词（中日英），Bing 返回 200 但没有可下载的音频直链，DDG 超时。所以现在响的是**程序合成的卡通喵叫**（`tools/gen_voice.py`）。原声是商业录音，即使搜到了，装进可分发的东西里也有法律问题。

### 你原来那条正路还在，随时能回去

**只要拿到一个出图 key**，就能做出真正"照特征重画"的高保真形象：

```powershell
# 1. 把 key 写进 C:\Users\hqh\.dsh\.credentials.yaml 的 refs 下
#      GEMINI_API_KEY: 你的key
# 2. 出定妆图
python tools/gen_art.py sheet --backend google
# 3. 用视觉模型逐条自检（10 条特征清单）
python tools/critique.py work/views/front.png
# 4. 按报告改 tools/gen_art.py 里的 CHAR，删掉 front.* 重跑第 2 步
# 5. 达标后出全部动作
python tools/gen_art.py actions
python tools/build_assets.py all
```

`tools/imggen.py` 已经做成**多 provider 自动探测**（Google AI Studio / OpenRouter / OfoxAI），换家只改环境变量，不动代码。出图需要的 prompt、角色描述、自检清单**全部已写好**。

---

## 四、重要：公开仓库与版权

你说"不公开发布、只本地用"。我据此做了处理，但**有一件事需要你知道**：

仓库 `github.com/Qihang-He/dsh-nyanko-sensei` **已经是 public 的**（那是按你早先"建公共仓库 + 提 PR"的授权建的）。今晚我把它清成了**纯代码与工具**：

- 移除了 `assets/anims/` 和 `assets/voice/` 下的所有内容（改为本地构建产物，gitignore 掉）
- 本地文件一个没动，13 个 webm + 7 个语音都还在
- **理由**：现在这些素材是从你给的**动画原画**派生的，属于版权作品，不能随公开仓库分发

**你回来后的两个选择**（我没有替你决定）：

1. **想要私密**：`gh repo edit Qihang-He/dsh-nyanko-sensei --visibility private --accept-visibility-change-consequences`
2. **保持公开**：现在就只含我自己写的代码与工具，可以安全公开。**但要注意**：`work/` 里有你的参考图原画，已被 gitignore，不会被推上去；`tools/CALIBRATION.md` 里描述了特征但没有图片。

另外 `docs/screenshot.png` 和 `docs/preview/*.gif` 含有从原画派生的画面，**也已从版本控制移除**（它们同样在 gitignore 覆盖下）。README 里的预览链接因此会失效——这是我留下的已知缺陷，见第七节。

---

## 五、技术记录：为什么抠图做不到（省你以后重走一遍）

你给的两张草地背景图（正面特写、趴姿）我一直没能干净抠出来。**七种算法全部失败**，根因是一个数值事实：

| 像素 | 归一化 RGB（除以自身亮度和） |
| --- | --- |
| 草地 | `≈ [0.35, 0.43, 0.22]` |
| 猫的奶白毛 | `≈ [0.35, 0.34, 0.31]` |

**归一化后只差约 0.1。** 也就是说，在排除亮度后的色彩空间里，猫的奶白毛和草地黄绿**几乎是同一个颜色**。任何"按颜色区分前后景"的方法都会一起中招：

1. **色距阈值** — 容差大到能盖住草地渐变，就一并盖住了猫的暖色毛。
2. **环形采样色距** — 同上，渐变不是几个采样点能覆盖的。
3. **饱和度判别** — 草地阴影是**去饱和的灰绿**，同时猫的**灰色斑块**也是低饱和，两者被判为同类。
4. **绿主导判别** — 同一问题反过来：灰绿阴影"不够绿"被留成前景，灰斑被误删。
5. **纯步进洪泛** — 动画原画的描边在部分位置是**一像素软边**，步进阈值会一小步一小步渗进猫体内，整只猫被泛洪。
6. **步进 + 全局双重约束洪泛** — 不渗了，但草地到处连通且贴边，泛洪覆盖不全，残留大片草。
7. **调色板学习匹配** — 从干净的样本学角色配色，再匹配其他图。门槛 26 时 **100% 像素**被判为角色——就是上面那个 0.1 的差距。

**结论**：除非有 AI 分割模型（需要 key）或你手动抠图，这两张图只能放弃。金色的那张背景是纯色平涂，所以能干净抠出——**它是唯一可用的素材，也是我现在用的那张**。

这些工具都留在 `tools/` 里了（`extract_refs.py`、`extract_hard.py`、`extract_border.py`、`palette_match.py`），以后想再试有不小参考价值。

---

## 六、语音怎么换成你想要的

机制已经做好，**放文件就行，不用改代码**：

```
%USERPROFILE%\.dsh\dsh-nyanko-sensei\voice\<语音包名>\<clip id>.<扩展名>
```

例：把原声剪成 `natsume.mp3` 丢进去，刷新页面，点击就叫它。
支持 `mp3/m4a/aac/ogg/oga/opus/wav/flac`，**用户目录优先于包内**。

也可以录：

```powershell
pwsh -File tools/record-voice.ps1 -Device       # 列出麦克风
pwsh -File tools/record-voice.ps1 -Clip natsume -Seconds 6
```

它会录音 → 剪掉首尾静音 → `loudnorm` 归一化 → 写进用户语音包。

clip id 与用途：`natsume`（点击主台词）、`happy`、`angry`、`surprised`、`eat`、`purr`、`sleep`。

**只在你本机用，别把商业录音那版提交到任何公开仓库。**

---

## 七、已知缺陷与明天可做的事

### 缺陷

1. ~~**README 里的预览图链接会失效**~~ — **已修**。两个 README 都已改为明确声明"仓库不含图片"并说明原因，列出本地构建后会出现的路径，且 13 个动作全部列出（原来只列了 3 个）。已核对：无残留内嵌图片，所有相对链接都能在磁盘上找到对应文件。
2. **走路腿不交替**——单素材的物理限制。
3. **语音是合成占位音**，不是原声。
4. **没有实现 `beast`（变身巨大白兽形态）**——代码里留了别名映射到 `surprised`，但没有真素材。
5. **`DEFAULTS` 里 `speed` 和 `showSettingsHint` 是死字段**，没有任何地方读，也没控件改。要么接上，要么删掉。

### 明天最值得做的三件事（按性价比排序）

1. **拿一个出图 key**（Google AI Studio 免费额度就行）。这是唯一能把还原度和动作生动度同时拉满的路，而且 prompt/描述/自检环我全写好了，跑几条命令就有。要走代理的话你自己方便，我这个会话说不了。
2. **补好语音**：自己剪一段 `natsume.mp3` 丢进用户语音包，立刻就有声音了。
3. **如想要私密**：把仓库转 private。

---

## 八、命令速查

```powershell
# 重新构建全部动作（素材来自 work/sprites/base.png）
cd D:\Deepseek_Harness\dsh-nyanko-sensei
python tools/gen_motion.py

# 逐帧审阅图（判断动作好坏看这个）
python tools/motion_sheet.py

# 重新生成占位语音
python tools/gen_voice.py

# 装/更新到 DSH
dsh plugin --profile web add "file:D:\Deepseek_Harness\dsh-nyanko-sensei"

# 验证
node tools/check-package.mjs
node tools/verify-browser.mjs

# 带 key 出图（你原来的正路）
python tools/gen_art.py sheet --backend google
python tools/critique.py work/views/front.png
```

---

## 九、最后一句

你要的"完全真实"，卡在**一个 key** 上，不是卡在实现上。我把能做的都做了、把不能做的原因都记下来了、把回去的路铺好了。明天你拿到 key，或者告诉我代理已经通，我就能把这条正路一次跑完。
