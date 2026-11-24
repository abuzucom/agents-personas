"""Check the AUDIT.md section 6 not-legal-advice line in one havel reply.

The line sits directly above the final verdict line in every mode. The
engine requires VERDICT_JSON as the last report line, so the line cannot
close the report as it did in the source workflow.
"""

from __future__ import annotations

DISCLAIMER = "NOT LEGAL ADVICE: engineering findings from a static review. Confirm with counsel."


def disclaimer_problem(response: str, verdict_label: str) -> str:
    """Return why the reply misplaces the disclaimer, or an empty string.

    The last line that starts with the verdict label decides, as in the
    engine gate. A reply quotes untrusted text, so an earlier verdict line
    with a disclaimer above it proves nothing.
    """
    lines = response.split("\n")
    prefix = f"{verdict_label}:"
    verdict_indexes = [index for index, line in enumerate(lines) if line.startswith(prefix)]
    if not verdict_indexes:
        return f"no {prefix} line, so the not-legal-advice line has no anchor"
    above = [line.strip() for line in lines[: verdict_indexes[-1]] if line.strip()]
    if not above or above[-1] != DISCLAIMER:
        return f"the line directly above the final {prefix} line must read exactly: {DISCLAIMER}"
    return ""
