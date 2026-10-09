#!/usr/bin/env bash
# Print the tools the gates use, with versions. Exit 1 if a required tool is
# missing, 2 if only optional ones are, 0 otherwise.
set -uo pipefail

required=(uv git)
optional=(docker gitleaks osv-scanner git-cliff shellcheck)

version_of() {
  case $1 in
    docker) docker version --format '{{.Client.Version}}' 2>/dev/null ;;
    gitleaks) gitleaks version 2>/dev/null ;;
    *) "$1" --version 2>/dev/null | head -1 ;;
  esac
}

rc=0
printf '%-12s %-9s %s\n' TOOL NEED VERSION
for t in "${required[@]}" "${optional[@]}"; do
  need=optional
  for r in "${required[@]}"; do [[ $r == "$t" ]] && need=required; done
  if command -v "$t" >/dev/null 2>&1; then
    printf '%-12s %-9s %s\n' "$t" "$need" "$(version_of "$t")"
  else
    printf '%-12s %-9s %s\n' "$t" "$need" "MISSING"
    if [[ $need == required ]]; then rc=1; elif ((rc == 0)); then rc=2; fi
  fi
done

if command -v docker >/dev/null 2>&1 && ! docker info >/dev/null 2>&1; then
  echo "docker is installed but the engine isn't reachable; database tests will be skipped."
  ((rc == 0)) && rc=2
fi
exit $rc
