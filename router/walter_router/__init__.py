"""Import name of the Walter Router module. Its code lives in the module's own folders at the module root
(research/, analysis/, interface/, serve/, store/, cli.py), so `walter_router.analysis.select` is <root>/analysis/select.py."""
from pathlib import Path

__path__ = [str(Path(__file__).resolve().parent.parent)]
