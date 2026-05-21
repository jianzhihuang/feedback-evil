#!/usr/bin/env python3
"""MCP server lifecycle guard tests."""

import json
import os

import psutil
import pytest

from mcp_feedback_enhanced import server


@pytest.mark.asyncio
async def test_interactive_feedback_is_content_only_tool():
    """interactive_feedback returns MCP content blocks, so it must not require structured output."""
    tools = await server.mcp.list_tools()
    feedback_tool = next(tool for tool in tools if tool.name == "interactive_feedback")

    assert feedback_tool.output_schema is None


def test_singleton_guard_replaces_stale_lock(monkeypatch, tmp_path):
    """測試 singleton guard 會覆寫已結束 PID 的舊 lock。"""
    lock_path = tmp_path / "feedback.lock"
    lock_path.write_text(json.dumps({"pid": 12345}), encoding="utf-8")

    def dead_process(pid):
        raise psutil.NoSuchProcess(pid)

    monkeypatch.setenv("MCP_FEEDBACK_SINGLETON", "true")
    monkeypatch.setenv("MCP_FEEDBACK_SINGLETON_LOCK", str(lock_path))
    monkeypatch.setattr(server.psutil, "Process", dead_process)

    activated_lock = server._activate_singleton_guard()

    assert activated_lock == lock_path
    assert json.loads(lock_path.read_text(encoding="utf-8"))["pid"] == os.getpid()

    server._release_singleton_guard(lock_path)
    assert not lock_path.exists()


def test_singleton_guard_terminates_old_feedback_process(monkeypatch, tmp_path):
    """測試 singleton guard 只會終止 feedback MCP 相關舊程序。"""
    lock_path = tmp_path / "feedback.lock"
    lock_path.write_text(json.dumps({"pid": 43210}), encoding="utf-8")

    class OldFeedbackProcess:
        def __init__(self):
            self.terminated = False
            self.killed = False

        def cmdline(self):
            return ["python", "-m", "mcp_feedback_enhanced.server"]

        def name(self):
            return "python"

        def terminate(self):
            self.terminated = True

        def wait(self, timeout):
            return 0

        def kill(self):
            self.killed = True

    old_process = OldFeedbackProcess()

    monkeypatch.setenv("MCP_FEEDBACK_SINGLETON", "true")
    monkeypatch.setenv("MCP_FEEDBACK_SINGLETON_LOCK", str(lock_path))
    monkeypatch.setattr(server.psutil, "Process", lambda pid: old_process)

    activated_lock = server._activate_singleton_guard()

    assert activated_lock == lock_path
    assert old_process.terminated is True
    assert old_process.killed is False
    assert json.loads(lock_path.read_text(encoding="utf-8"))["pid"] == os.getpid()

    server._release_singleton_guard(lock_path)
