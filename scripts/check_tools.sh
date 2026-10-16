#!/usr/bin/env bash
# Print the tools the gates use, with versions. Exit 1 if a required tool is
# missing, 2 if only optional ones are (or no container runtime is reachable), 0 otherwise.
# Any one runtime is enough; the others are listed for scripts/compare_runtimes.sh.
set -uo pipefail

required=(uv git)
optional=(gitleaks osv-scanner git-cliff shellcheck)
runtimes=(docker podman nerdctl)
alternatives=(podman-compose buildah incus)

version_of() {
  case $1 in
    docker) docker version --format '{{.Client.Version}}' 2>/dev/null ;;
    incus) incus version 2>/dev/null | head -1 ;;
    gitleaks) gitleaks version 2>/dev/null ;;
    shellcheck) shellcheck --version 2>/dev/null | sed -n 's/^version: //p' ;;
    *) "$1" --version 2>/dev/null | head -1 ;;
  esac
}

rc=0
printf '%-15s %-9s %s\n' TOOL NEED VERSION
for t in "${required[@]}" "${optional[@]}"; do
  need=optional
  for r in "${required[@]}"; do [[ $r == "$t" ]] && need=required; done
  if command -v "$t" >/dev/null 2>&1; then
    printf '%-15s %-9s %s\n' "$t" "$need" "$(version_of "$t")"
  else
    printf '%-15s %-9s %s\n' "$t" "$need" "MISSING"
    if [[ $need == required ]]; then rc=1; elif ((rc == 0)); then rc=2; fi
  fi
done

reachable=
for t in "${runtimes[@]}" "${alternatives[@]}"; do
  if ! command -v "$t" >/dev/null 2>&1; then
    printf '%-15s %-9s %s\n' "$t" runtime "-"
  elif [[ " ${runtimes[*]} " == *" $t "* ]] && ! "$t" info >/dev/null 2>&1; then
    printf '%-15s %-9s %s\n' "$t" runtime "$(version_of "$t") (engine not reachable)"
  else
    printf '%-15s %-9s %s\n' "$t" runtime "$(version_of "$t")"
    [[ " ${runtimes[*]} " == *" $t "* ]] && reachable+=" $t"
  fi
done
if [[ -z $reachable ]]; then
  echo "No container runtime reachable; database tests need one or LABRA_TEST_DATABASE_URL."
  ((rc == 0)) && rc=2
fi
exit $rc
