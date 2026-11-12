"""DSH 插件壳的 Node 契约测试入口。

壳的订阅行为(尤其是子 agent 的 turn/end)只能在 JS 层断言,所以真正的用例在
`tests/dsh_shell.test.mjs`;这里负责在 pytest 里跑它,让 CI 一并覆盖。
没有 node 的环境跳过,不阻塞 Python 侧测试。
"""
import os
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
SHIM = os.path.join(HERE, "..", "shims", "dsh", "index.js")


def test_shell_has_tests():
    assert os.path.exists(os.path.join(HERE, "dsh_shell.test.mjs"))
    assert os.path.exists(SHIM)


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_dsh_shell_contract():
    proc = subprocess.run(
        ["node", "--test", os.path.join(HERE, "dsh_shell.test.mjs")],
        cwd=HERE, capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
