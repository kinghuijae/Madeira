#!/usr/bin/env python3
"""Exercise the actual release condition, including skipped build dependencies."""

import ast
import itertools
import re
from pathlib import Path


repo = Path(__file__).resolve().parents[2]
workflow = (repo / ".github/workflows/build.yml").read_text(encoding="utf-8")
jobs = dict(re.findall(r"^  ([a-z0-9_-]+):\n(.*?)(?=^  [a-z0-9_-]+:|\Z)",
                       workflow, re.M | re.S))
release = jobs["release"]
condition = re.search(r"^    if: >-\n(.*?)^    runs-on:", release, re.M | re.S)[1].strip()
assert condition.startswith("${{") and condition.endswith("}}")
expression = condition[3:-2].strip()
assert "!cancelled()" in expression, "Skipped dependencies require an explicit status check"
fields = ("github.repository", "github.ref", "github.event_name", "cancelled()",
          "needs.plan.result", "needs.app.result", "needs.reuse.result")
for index, field in enumerate(fields):
    expression = expression.replace(field, f"value_{index}")
expression = expression.replace("&&", " and ").replace("||", " or ").replace("!", " not ")
tree = ast.parse(" ".join(expression.split()), mode="eval")
allowed = (ast.Expression, ast.BoolOp, ast.UnaryOp, ast.Compare, ast.Name,
           ast.Load, ast.Constant, ast.And, ast.Or, ast.Not, ast.Eq)
assert all(isinstance(node, allowed) for node in ast.walk(tree)), "Unsupported gate syntax"
code = compile(tree, "release.if", "eval")
statuses = ("success", "failure", "cancelled", "skipped")
cases = itertools.product(
    ("kinghuijae/Madeira", "willfaust/Madeira"),
    ("refs/heads/main", "refs/heads/codex/pr-build-test"),
    ("push", "workflow_dispatch", "pull_request", "workflow_run"),
    (False, True), statuses, statuses, statuses,
)
count = 0
for values in cases:
    repository, ref, event, cancelled, plan, app, reuse = values
    expected = (
        (repository, ref) == ("kinghuijae/Madeira", "refs/heads/main")
        and event in ("push", "workflow_dispatch")
        and not cancelled and plan == "success"
        and (app, reuse) in (("success", "skipped"), ("skipped", "success"))
    )
    actual = eval(code, {"__builtins__": {}},
                  {f"value_{index}": value for index, value in enumerate(values)})
    assert actual == expected, f"Release gate mismatch: {values}: {actual} != {expected}"
    count += 1

assert "needs: [plan, app, reuse]" in release
assert re.search(r"^permissions:\n  contents: read$", workflow, re.M)
for name, job in jobs.items():
    assert ("contents: write" in job) == (name == "release"), name
assert "persist-credentials: false" in release
assert "ref: ${{ github.sha }}" in release
download = release.split("uses: actions/download-artifact@v4", 1)[1].split("- name:", 1)[0]
assert "name: Madeira-ipa" in download and "path: dist" in download
assert not any(option in download for option in ("run-id:", "repository:", "github-token:"))
assert release.index("runtime-components.py ipa") < release.index("publish-release.sh")
publisher = (repo / "tools/build/publish-release.sh").read_text(encoding="utf-8")
assert publisher.index('test "$asset"') < publisher.index("gh release edit")
assert '--target "$GITHUB_SHA"' in publisher
assert "${GITHUB_RUN_NUMBER}-${GITHUB_RUN_ATTEMPT}-${GITHUB_SHA:0:7}" in publisher
assert "--draft --prerelease --latest=false" in publisher
assert "--draft=false --prerelease --latest=false" in publisher
assert "cancel-in-progress: ${{ github.ref != 'refs/heads/main' }}" in workflow
print(f"CI release checks passed ({count} publication conditions).")
