---
name: ziwei-fortune
description: "紫微斗数命盘排盘与运势分析。Use when: user asks about fortune, 运势, 紫微斗数, 命盘, 算命, 八字, destiny, astrology chart. NOT for: western astrology, tarot."
metadata:
  openclaw:
    emoji: "🔮"
    requires:
      bins: ["python3"]
user-invocable: true
---

# 紫微斗数运势预测

使用 `exec` tool 运行 `ziwei_fortune.py` 脚本排盘，然后基于命盘进行运势分析。

## Script Location

脚本位于 `skills/ziwei-fortune/ziwei_fortune.py`（相对于 bot 工作目录）。

## Usage

注意：sxtwl 依赖 C++ 编译，可能在 uv venv 中不可用。优先使用 conda python。

```bash
# 阳历日期（默认）
/Users/sen/miniconda3/bin/python skills/ziwei-fortune/ziwei_fortune.py 1990-8-16 -t 寅 -g 男

# 农历日期
/Users/sen/miniconda3/bin/python skills/ziwei-fortune/ziwei_fortune.py 1990-6-26 -t 寅 -g 男 --lunar

# 农历闰月
/Users/sen/miniconda3/bin/python skills/ziwei-fortune/ziwei_fortune.py 1990-6-26 -t 寅 -g 女 --lunar --leap

# JSON 输出（结构化，便于深度分析）
/Users/sen/miniconda3/bin/python skills/ziwei-fortune/ziwei_fortune.py 1990-8-16 -t 寅 -g 男 --json
```

## 收集用户信息

排盘需要三项信息：

1. **出生日期** — 格式 YYYY-M-D，确认是阳历还是农历
2. **出生时辰** — 十二地支（子丑寅卯辰巳午未申酉戌亥）或 0-11
3. **性别** — 男 or 女

**时辰对照表（用户给钟点时间时转换）：**

| 时辰 | 时间 | 值 |
|------|------|---|
| 子时 | 23:00-01:00 | 0 |
| 丑时 | 01:00-03:00 | 1 |
| 寅时 | 03:00-05:00 | 2 |
| 卯时 | 05:00-07:00 | 3 |
| 辰时 | 07:00-09:00 | 4 |
| 巳时 | 09:00-11:00 | 5 |
| 午时 | 11:00-13:00 | 6 |
| 未时 | 13:00-15:00 | 7 |
| 申时 | 15:00-17:00 | 8 |
| 酉时 | 17:00-19:00 | 9 |
| 戌时 | 19:00-21:00 | 10 |
| 亥时 | 21:00-23:00 | 11 |

**日历判断：**
- 用户说阳历/公历/身份证上的日期 → 默认（不加 --lunar）
- 用户说农历/阴历 → 加 --lunar
- 不确定时，主动询问

## 分析指南

排盘后用中文进行全面分析，依次覆盖：

1. **命盘概览** — 命宫/身宫位置、命主/身主星、五行局、四柱
2. **重点宫位分析** — 命宫（性格）、财帛宫（财运）、官禄宫（事业）、夫妻宫（感情）、福德宫（心态）、迁移宫（外在环境）
3. **格局与四化** — 禄权科忌飞星、三方四正组合、杀破狼/机月同梁等格局
4. **大限运势** — 根据用户当前年龄分析当前大限及即将到来的转折
5. **建议** — 事业方向、感情提示、理财倾向、注意事项

**分析风格：**
- 用中文回复
- 引用具体星曜和亮度（庙/旺/得/利/平/不/陷）支撑分析
- 平衡呈现优势与挑战，避免绝对判断
- 用"倾向于""适合""需注意"等措辞
- 如用户只问特定方面（感情/事业/财运），聚焦该方面深入分析

## 当用户模糊提问时

- "帮我算算" → 先询问生辰八字信息
- "我的运势怎么样" → 收集信息后全面分析
- "最近感情不顺" → 收集信息后聚焦夫妻宫和福德宫分析
- "事业发展如何" → 收集信息后聚焦官禄宫和财帛宫分析
