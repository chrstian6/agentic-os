from runtime import classify


def test_trivial_task_is_level_one():
    c = classify.classify("rename the variable foo to bar")
    assert c["difficulty"]["level"] == 1, c["difficulty"]
    assert c["depth"] == 1
    assert c["agents"] == ["builder"]


def test_complex_task_escalates():
    c = classify.classify("rewrite the distributed job scheduler to fix a race condition "
                          "across multiple services with a schema migration", file_count=30)
    assert c["difficulty"]["level"] >= 4, c["difficulty"]
    assert "REVIEW" in c["workflow"]


def test_risk_floor_raises_workflow_depth():
    """Risk may deepen the workflow even when the code change is small."""
    c = classify.classify("update the stripe payment webhook secret")
    assert c["risk"]["level"] in ("high", "critical"), c["risk"]
    assert c["depth"] >= int(c["risk"]["workflow_floor"]), c
    assert c["depth"] >= c["difficulty"]["level"], c
    # and the floor is what does the work for an otherwise ordinary edit
    plain = classify.classify("update the webhook url")
    assert plain["depth"] < c["depth"], (plain["depth"], c["depth"])


def test_destructive_task_is_critical():
    r = classify.risk("drop table users in production and delete the backups")
    assert r["level"] == "critical", r
    assert r["workflow_floor"] == 4


def test_reclassification_only_escalates():
    first = classify.classify("fix the typo in the button label")
    second = classify.reclassify(first, "hidden dependency on the auth session",
                                 "fix the typo in the button label", extra_level=2)
    assert second["depth"] > first["depth"], (first["depth"], second["depth"])
    assert second["reclassification_reason"]
    assert second["reclassified_from"] == first["depth"]


def test_skill_budget_scales_with_depth():
    small = classify.classify("fix a typo")
    big = classify.classify("redesign the entire application architecture and migrate "
                            "the database schema", file_count=40)
    assert small["skill_budget"] < big["skill_budget"]


def test_ordinary_feature_work_is_not_trivial():
    """Product work must not fall through to level 1 just because it reads simply."""
    for prompt in ("add a graduation-year filter to the alumni list page",
                   "add a settings form for notification preferences",
                   "build a table of recent signups with sorting"):
        c = classify.classify(prompt)
        assert c["difficulty"]["level"] >= 2, (prompt, c["difficulty"])


def test_genuinely_trivial_prompts_stay_trivial():
    for prompt in ("fix the typo in the nav label", "rename the variable foo to bar",
                   "update the comment above parseDate"):
        assert classify.classify(prompt)["difficulty"]["level"] == 1, prompt


def test_agent_and_automation_work_is_not_trivial():
    """Agents, schedulers and multi-service integrations must not read as level 1.

    These used to score 1.0 because only "build " matched: the classifier had no
    vocabulary for agentic work, scheduled jobs, document extraction, or named services.
    """
    for prompt in ("build an agent that triages the Outlook inbox via Microsoft Graph "
                   "and files quote requests into SharePoint job folders",
                   "build a scheduled agent that scans every job folder, extracts job details "
                   "into an Excel workbook, and emails a weekly exception report of overdue jobs",
                   "build an AI agent with tool use that drafts replies to customer emails"):
        c = classify.classify(prompt)
        assert c["difficulty"]["level"] >= 3, (prompt, c["difficulty"])


def test_named_service_integrations_are_not_trivial():
    for prompt in ("write a cron job that pulls cost centres from the Simpro API and flags "
                   "jobs over budget",
                   "sync new SharePoint documents into the jobs database every morning"):
        c = classify.classify(prompt)
        assert c["difficulty"]["level"] >= 2, (prompt, c["difficulty"])


def test_mentioning_email_or_a_service_alone_stays_trivial():
    for prompt in ("fix the typo in the email subject line",
                   "rename the outlook folder variable"):
        assert classify.classify(prompt)["difficulty"]["level"] == 1, prompt


def test_signals_match_at_word_starts_not_inside_words():
    """"ui" must not fire on "build", nor "form" on "platform", nor "test" on "latest"."""
    d = classify.difficulty("build the latest platform release notes")
    for hit in d["signals"]:
        assert not hit.startswith(("visual:ui", "scope:form", "testing:test")), d["signals"]
    # Stems still match the words they start.
    d = classify.difficulty("optimize the concurrent scheduler")
    assert "reasoning:optimi(+1)" in d["signals"], d["signals"]


def test_risk_stems_do_not_match_inside_other_words():
    # 1.8.5: "strip" is not "stripe", "wip" is not "wipe".
    for task in ("strip whitespace from the search input", "commit the wip branch"):
        assert classify.classify(task)["risk"]["level"] == "normal", task
    assert classify.classify("issue a refund through stripe")["risk"]["level"] in ("high", "critical")
