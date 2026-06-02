"""Skill 系统 —— 预定义角色 / 子代理。

Skills 是 Markdown 文件，存放在 skills/ 目录下，
包含 YAML frontmatter（元数据）+ Markdown body（指令）。

两种执行模式:
  inject  — body 直接注入用户消息，主 Agent 执行（轻量）
  subagent — 独立 Agent，限制工具集，隔离上下文（重量）
"""
