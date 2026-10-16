"""Enterprise AI Software Factory — Kernel package."""
from .kernel import Kernel, KernelError
from .state import JobState, StateError, verify_chain
from .lease import LeaseManager, LeaseError
from .schemas import SchemaStore, SchemaError
from .profiles import load_profile, validate_profile, ProfileError
from .engine import Engine, EngineError
from .checks import CheckResult, CheckError, run_checks, summarise
from .adapters import Adapter, AdapterError, RunResult, discover_adapters
from .checkpoint import result_hash, tree_hash
from .conformance import CaseResult, overall_ok, run_suite
from .dashboard import build_view, export_dashboard, render_html

__all__ = [
    "Kernel",
    "KernelError",
    "JobState",
    "StateError",
    "verify_chain",
    "LeaseManager",
    "LeaseError",
    "SchemaStore",
    "SchemaError",
    "load_profile",
    "validate_profile",
    "ProfileError",
    "Engine",
    "EngineError",
    "CheckResult",
    "CheckError",
    "run_checks",
    "summarise",
    "Adapter",
    "AdapterError",
    "RunResult",
    "discover_adapters",
    "result_hash",
    "tree_hash",
    "CaseResult",
    "overall_ok",
    "run_suite",
    "build_view",
    "export_dashboard",
    "render_html",
]
__version__ = "0.4.0"
