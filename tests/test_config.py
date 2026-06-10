"""Path / bundled-asset resolution. Run: uv run python tests/test_config.py

No pytest dependency — plain asserts. Verifies that a pip-installed earworm (whose
working dir has no prompts/) resolves prompts from the packaged assets, while a
source/clone checkout uses its local prompts/.
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from earworm import config  # noqa: E402
from earworm.config import paths  # noqa: E402


def _home(tmp: str):
    os.environ["EARWORM_HOME"] = tmp
    paths.cache_clear()
    return paths()


def test_prompts_uses_local_dir_when_present(tmp: str) -> None:
    p = _home(tmp)
    (p.root / "prompts").mkdir()  # use the resolved root (tmp may be a symlink)
    assert p.prompts == p.root / "prompts"
    assert p.prompts != config._ASSETS / "prompts"


def test_prompts_falls_back_to_bundled_when_absent(tmp: str) -> None:
    p = _home(tmp)  # empty home — no prompts/ dir
    assert not (Path(tmp) / "prompts").exists()
    assert p.prompts == config._ASSETS / "prompts", "must resolve to the packaged prompts"


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        with tempfile.TemporaryDirectory() as tmp:
            try:
                t(tmp)
                print(f"  ok  {t.__name__}")
            except AssertionError as e:
                failed += 1
                print(f"FAIL  {t.__name__}: {e}")
            finally:
                os.environ.pop("EARWORM_HOME", None)
                paths.cache_clear()
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
