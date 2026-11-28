"""The owner's HIG standard is the design default and wins its conflicts."""
from runtime import router


def test_design_task_routes_hig_taste_and_drops_the_conflicting_skill():
    for task in ("redesign the settings page layout", "polish the dashboard typography",
                 "build a landing page for the spring sale"):
        r = router.route(task, agent="builder")
        assert "builder/hig-taste" in r["loaded"], (task, r["loaded"])
        assert "builder/design-taste" not in r["loaded"], (task, r["loaded"])
        assert "builder/hallmark" not in r["loaded"], (task, r["loaded"])


def test_backend_task_does_not_load_it():
    r = router.route("add an index to the bids table query", agent="builder")
    assert "builder/hig-taste" not in r["loaded"], r["loaded"]


def test_cleanup_and_docs_tasks_do_not_load_it():
    for task in ("clean up dead code in utils", "polish the readme",
                 "make the error messages readable", "tidy the generic error handler"):
        r = router.route(task, agent="builder")
        assert "builder/hig-taste" not in r["loaded"], (task, r["loaded"])
