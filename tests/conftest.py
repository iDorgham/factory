"""Shared pytest fixtures for the factory kernel test suite."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
KERNEL_SRC = REPO_ROOT / "kernel" / "src"


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def schemas_dir(repo_root: Path) -> Path:
    return repo_root / "kernel" / "schemas"


@pytest.fixture
def factory_root(tmp_path: Path) -> Path:
    """A hermetic factory tree: config + schemas + presets + stages."""
    root = tmp_path / "factory"
    (root / "kernel").mkdir(parents=True)
    for sub in ("schemas", "presets", "stages"):
        shutil.copytree(REPO_ROOT / "kernel" / sub, root / "kernel" / sub)
    shutil.copytree(REPO_ROOT / "adapters", root / "adapters")
    shutil.copy(REPO_ROOT / "factory.json", root / "factory.json")
    return root


@pytest.fixture
def kernel(factory_root: Path):
    from factory_kernel.kernel import Kernel

    return Kernel(factory_root)


@pytest.fixture
def demo_job(kernel):
    """A project and a freshly created job."""
    kernel.project_create("demo", mode="solo", domain="web")
    job = kernel.job_run("demo", "Build a landing page")
    return kernel, job
