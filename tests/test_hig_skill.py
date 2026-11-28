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
                 "make the error messages readable", "tidy the generic error handler",
                 "fix the cron job screen scraping retry", "add stripe credit card refunds endpoint"):
        r = router.route(task, agent="builder")
        assert "builder/hig-taste" not in r["loaded"], (task, r["loaded"])


def test_everyday_ui_asks_load_it():
    for task in ("make the settings page cleaner and more readable", "polish the pricing card",
                 "the font on the lot page feels too big", "the modal padding is cramped",
                 "fix the spacing on the checkout form so it looks less generic"):
        r = router.route(task, agent="builder")
        assert "builder/hig-taste" in r["loaded"], (task, r["loaded"])
