# Publish Metrics Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** View published content metrics per platform in publish center, synced daily.

**Architecture:** Extend `publish_jobs`, add snapshot + sync run tables, Xiaohongshu metrics adapter via Playwright, APScheduler cron in publish worker, REST API + publish center tab.

**Tech Stack:** SQLAlchemy, FastAPI, APScheduler, Playwright, vanilla JS

---

### Task 1: Data model + migrations ✅
### Task 2: Post matcher + snapshot store (TDD) ✅
### Task 3: Xiaohongshu parser + sync orchestrator (TDD) ✅
### Task 4: API routes + worker cron ✅
### Task 5: Publish center UI tab ✅
### Task 6: Other platforms (douyin/kuaishou/wechat) ✅
### Task 7: Summary API + cards + trend chart UI (P3) ✅
