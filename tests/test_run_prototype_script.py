from __future__ import annotations

import os
import subprocess
from pathlib import Path


def test_zero_argument_start_uses_bundled_sample() -> None:
    project_root = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    environment["FACE_WATCH_CHECK_ONLY"] = "1"

    result = subprocess.run(
        [str(project_root / "scripts/run_prototype.sh")],
        cwd=project_root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "examples/sample.mp4" in result.stdout
    assert "examples/reference.jpeg" in result.stdout
    assert "目标人物（老许）" in result.stdout
    assert (project_root / "examples/sample.mp4").is_file()
    assert (project_root / "examples/reference.jpeg").is_file()
