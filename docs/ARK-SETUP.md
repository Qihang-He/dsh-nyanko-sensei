# 火山方舟开通步骤（豆包 Seedream / Seedance）

一分钟搞定，全程国内手机号 + 支付宝，不需要代理。

---

## 1. 注册并开通模型

打开 **https://console.volcengine.com/ark**

- 用手机号注册 / 登录（火山引擎账号，抖音账号也能直接登）
- 左侧进入 **「开通管理」**
- 找到并**开通**这两个模型：
  - **图片生成** → `Doubao-Seedream`（做角色定妆图和分镜图）
  - **视频生成** → `Doubao-Seedance`（做需要真实关节运动的动作）

> 只开通图片也能跑，视频那步先跳过，见下面第 4 节。

---

## 2. 创建 API Key

左侧 **「API Key 管理」** → **创建 API Key** → 复制。

**这个 key 只显示一次**，务必当场复制。

---

## 3. 把 key 交给本项目

两种方式，任选：

**方式 A：写进 DSH 凭据库**（推荐，和现有 key 放一起）

编辑 `C:\Users\hqh\.dsh\.credentials.yaml`，在 `refs:` 下加一行：

```yaml
refs:
  OFOX_API_KEY: sk-of-...
  ARK_API_KEY: 你的新key
```

**方式 B：环境变量**

```powershell
setx ARK_API_KEY "你的新key"
```

> 环境变量优先级更高。`setx` 之后**要新开一个终端**才生效。

---

## 4. 验证

```powershell
cd D:\Deepseek_Harness\dsh-nyanko-sensei
python tools/platform.py --check
```

期望输出：

```
ARK_API_KEY       configured (xxxx...xxxx)
image generation  OK
```

**如果返回 401 / 403**：key 是对的，但账号没开通对应模型——回第 1 步检查「开通管理」。
**如果返回 `not configured`**：key 没被读到，检查上面两种方式哪一步漏了。

---

## 5. 花钱之前先看计划

```powershell
python tools/spend_plan.py      # CNY 20 怎么分配
python tools/platform.py --plan --budget 20   # 同一批次的账单预估
```

`spend_plan.py` 说明钱花在哪、为什么这么分；`--plan` 给出逐项价格。

---

## 6. 干跑一次（不花钱）

任何付费命令都支持 `--dry-run`，它会走完流程但不发请求：

```powershell
python tools/platform.py --image work/tmp.png "test" --dry-run --budget 20
```

预算超限时命令会**直接拒绝执行并告诉你还差多少**，不会默默花掉。

---

## 价格参考（2026-09，以控制台账单为准）

| 模型 | 单价 |
| --- | --- |
| Seedream 4.0 图片 | 约 **¥0.20 / 张** |
| Seedance 2.0 视频 | 约 **¥1.00 / 秒** |
| Seedance 2.0 mini 视频 | 约 **¥0.50 / 秒** |

**注意**：价格是 `tools/platform.py` 里的**输入参数**，不是账单真值。控制台账单才是准的；
如果价格变了，改 `tools/platform.py` 顶部的 `PRICE_PER_IMAGE` 和
`PRICE_PER_VIDEO_SECOND` 两个常量，预算闸和计划工具会跟着变。

---

## 下一步

key 配好之后告诉我，我跑：

1. **出角色定妆图**（用你给的参考图做条件输入，最多重试 8 次）
2. **你确认形象**（这一步必须你看，我看不出"像不像"的价值判断）
3. 出 13 个动作的分镜图
4. 对 walk / hop / happy / angry 出 2 秒视频，抠像转成透明帧
5. 重建素材、回归验证

第 2 步是花小钱验大方向的地方——如果形象不对，视频那 ¥8 就不花。
