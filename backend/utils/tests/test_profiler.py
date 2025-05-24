import time
from ..profiler import Profiler, profiled_function, _profile_cache


def test_profiler_elapsed_and_report():
    profiler = Profiler()
    time.sleep(0.001)
    elapsed = profiler.elapsed()
    assert isinstance(elapsed, float) and elapsed > 0

    msg = profiler.report("TestBlock")
    assert "TestBlock:" in msg and msg.endswith(" ms")


def test_profiled_function_caches_stats(tmp_path):
    # clear global cache
    _profile_cache.clear()

    @profiled_function(is_entry=True)
    def entry():
        quick()

    @profiled_function()
    def quick():
        pass

    entry()
    # entry key should be module.entry
    key = f"{entry.__module__}.entry"
    assert key in _profile_cache
    stats = _profile_cache[key]
    assert "quick" in stats
    assert stats["quick"]["nb_calls"] == 1
