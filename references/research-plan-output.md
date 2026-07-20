# Research Plan Output Contract

Use this reference only after Gate 6 reaches drafting or saving.

## Plan Template

```markdown
---
tags:
  - research-plan
  - <domain-tag>
created: YYYY-MM-DD
status: draft
---

# <研究方向>

## 1. 研究问题

- **核心问题**: <precise, falsifiable question>
- **动机**: <grounded gap and why it matters>
- **范围**: <explicit in-scope and out-of-scope>

## 2. 创新点

1. <specific contribution and expected measurable effect>
2. <distinct contribution>

## 3. 方法路线

### 3.1 总体框架

<end-to-end data and model flow>

### 3.2 关键模块

1. **<module>**: <role, design choice, rejected alternative>
2. **<module>**: <role, design choice, rejected alternative>

### 3.3 技术难点与对策

| 难点 | 对策 | 验证方式 |
|---|---|---|
| <challenge> | <mitigation> | <check> |

## 4. 实验设计

- **Datasets**: <dataset, split, reason>
- **Baselines**: <method and comparison rationale>
- **Primary metrics**: <metric and success threshold>
- **Secondary metrics**: <metric>
- **Minimum falsification test**: <cheapest decisive experiment>
- **Ablations**: <component → isolated hypothesis>
- **Qualitative analysis**: <visualization or case study>

## 5. 时间规划

| 阶段 | 可验证交付物 | 预计时间 |
|---|---|---|
| 基线搭建 | <artifact/check> | <estimate> |
| 核心方法 | <artifact/check> | <estimate> |
| 实验与写作 | <artifact/check> | <estimate> |

## 6. 关键参考文献

- [[300 Resources/320 References/<filename>|<display>]] — <why critical>

## 7. 风险与备选

| 风险 | 概率 | 触发信号 | 备选方案 |
|---|---|---|---|
| <risk> | 高/中/低 | <observable signal> | <concrete plan B> |

---
> 基于已确认文献和头脑风暴生成于 YYYY-MM-DD。
```

## Index Contract

Create the index if absent; otherwise update the matching plan row in place.

```markdown
---
tags:
  - index
  - research-plan
cssclasses:
  - rightlane
---

# 研究计划合集

| 计划 | 状态 | 创建日期 | 关键方向 |
|---|---|---|---|
| [[<研究方向>]] | draft | YYYY-MM-DD | <domain, method> |
```

Use absolute vault-root paths inside paper wikilinks. In Markdown tables, escape the wikilink pipe as `\|`; outside tables, use the normal `|` separator.
