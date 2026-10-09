#!/usr/bin/env bash
# Run a gate inside a git hook: exit 2 ("unchecked") is reported but doesn't block.
# ci_local.sh calls the gates directly, so there the same exit shows as WARN.
"$@"
rc=$?
((rc == 2)) && exit 0
exit $rc
