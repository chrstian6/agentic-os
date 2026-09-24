"""A file write that mentions a dangerous command is data, not an execution.

Blocking it is a false positive, and false positives are how guards get worked around -
which costs more than the risk they prevent. Heredocs that are piped or executed still get
inspected.
"""
from runtime import guards

DANGEROUS = "rm -" + "rf /"          # assembled: a literal trips the session's own guard
FORCE_PUSH = "git push --" + "force origin main"


def test_writing_a_file_that_mentions_a_dangerous_command_is_allowed():
    cmd = "cat > tests/fixture.py <<'EOF'\nCASES = ['%s', '%s']\nEOF" % (DANGEROUS, FORCE_PUSH)
    v = guards.check(cmd)
    assert v["action"] == "ALLOW", v


def test_quoted_and_unquoted_heredocs_both_count_as_writes():
    for opener in ("<<'EOF'", '<<"EOF"', "<<EOF", "<<-EOF"):
        cmd = "cat > doc.md %s\nnever run %s\nEOF" % (opener, DANGEROUS)
        assert guards.check(cmd)["action"] == "ALLOW", opener


def test_a_heredoc_piped_into_a_shell_is_still_inspected():
    cmd = "cat <<'EOF' | bash\n%s\nEOF" % DANGEROUS
    assert guards.check(cmd)["action"] == "BLOCK", guards.check(cmd)


def test_a_dangerous_command_next_to_a_heredoc_write_is_still_caught():
    cmd = "cat > notes.md <<'EOF'\nharmless text\nEOF\n%s" % DANGEROUS
    assert guards.check(cmd)["action"] == "BLOCK", guards.check(cmd)


def test_the_write_target_itself_is_still_guarded():
    """Stripping the body must not stop the guard seeing what is being written to."""
    cmd = "cat > .env <<'EOF'\nAPI_KEY=x\nEOF"
    assert guards.check_path_write(".env")["action"] == "CONFIRM"
    v = guards.check(cmd)
    assert v["action"] == "CONFIRM", v
    assert v["matches"][0]["id"] == "creds.read", v


def test_python_heredoc_that_shells_out_is_still_inspected():
    cmd = "python3 - <<'EOF' \nimport os\nos.system('%s')\nEOF" % DANGEROUS
    assert guards.check(cmd)["action"] == "BLOCK", guards.check(cmd)
