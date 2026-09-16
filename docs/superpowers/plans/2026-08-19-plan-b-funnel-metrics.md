# Plan B Funnel Metrics Implementation Plan

> **For agentic workers:** Execute inline in this session. TDD per task.

**Goal:** Capture completion / 3s / watch / follow funnel metrics, change voiceover and WeChat description to match official signals, and declare AI-generated content on Douyin publish.

**Architecture:** Extend existing `PostMetricsItem` + snapshot columns; parsers pick extra keys when creator APIs send them. Copy changes stay in `content_methodology` / prompts. Douyin form adds an AI-declaration click before publish.

**Tech Stack:** SQLAlchemy, Playwright form helpers, pytest, vanilla JS publish center.

## Global Constraints

- Do not pause Kuaishou auto-publish; do not add Kuaishou-specific templates.
- Do not restore 突发！/炸裂！ hard openings.
- Rates stored as 0–100 floats; missing values stay NULL.
- AI declaration must not fail the whole publish if the control is absent.

---

### Task 1: Funnel metric fields

Parse and persist `follow_count`, `play_3s_rate`, `completion_rate`, `avg_watch_sec`, `profile_click_count`.

### Task 2: Copy funnel

Voiceover: fact hook in first 3 seconds, 小牛说 after; end with a commentable question. WeChat description leads with `sub_title`.

### Task 3: Douyin AI declaration

Click 自主声明 → 内容由AI生成 before 发布. Missing control is a warning, not a hard fail.
