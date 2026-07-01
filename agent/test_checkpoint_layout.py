#!/usr/bin/env python3
"""R1-2 checkpoint_layout 单元测试（无网络）。"""

from pathlib import Path

from checkpoint_layout import (
    checkpoint_int_from_filename,
    checkpoint_int_from_spec,
    logs_export_dir,
    model_path_in_logs,
)


def test_paths() -> None:
    job = Path("/tmp/job")
    assert logs_export_dir(job, "x1_dh_stand", "run_a") == Path(
        "/tmp/job/logs/x1_dh_stand/exported_data/run_a",
    )
    assert model_path_in_logs(job, "x1_dh_stand", "run_a", 3000) == Path(
        "/tmp/job/logs/x1_dh_stand/exported_data/run_a/model_3000.pt",
    )


def test_checkpoint_parse() -> None:
    assert checkpoint_int_from_filename("model_3000.pt") == 3000
    assert checkpoint_int_from_spec("3000", "model_3000.pt") == 3000
    assert checkpoint_int_from_spec("latest", "model_3000.pt") == 3000


if __name__ == "__main__":
    test_paths()
    test_checkpoint_parse()
    print("test_checkpoint_layout passed")
