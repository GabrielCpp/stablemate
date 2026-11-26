from paddock.names import RunName


def test_two_rounds_of_one_task_never_share_a_run_id() -> None:
    first = RunName("bench", "story", "a" * 40, "b" * 40, 1)
    rerun = RunName("bench", "story", "c" * 40, "b" * 40, 1)

    assert first.run_id("api") == f"story-{'a' * 12}-{'b' * 12}-1-api"
    assert first.run_id() != rerun.run_id()
    assert first.run_id() != RunName("bench", "story", "a" * 40, "b" * 40, 2).run_id()
