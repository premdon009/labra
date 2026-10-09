#!/usr/bin/env bash
# commit-msg hook: strip AI attribution trailers, then require a tracker ID in the subject.
#   <type>(<scope>): <ID>[ <ID>…] <summary>     e.g. feat(billing): M07 part payment
set -uo pipefail
msg_file=$1

# AGENTS.md rule 5: no AI attribution trailers.
sed -i -E '/^Co-Authored-By:.*(Claude|anthropic|Copilot|openai|ChatGPT|Gemini|Cursor|aider)/Id' "$msg_file"
sed -i -E '/^🤖 Generated with/d' "$msg_file"

subject=$(grep -vE '^\s*(#|$)' "$msg_file" | head -1)
case $subject in Merge*|Revert*|fixup!*|squash!*) exit 0 ;; esac

id='(W[0-9]{2}|M[0-9]{2}|X[0-9]{2}|LT[0-9]{2}|R[0-9]{2})(\.[0-9]+)?|EC-[A-O][0-9]{2}'
if ! grep -qE "^[a-z]+(\([a-z0-9._-]+\))?!?: (${id})( |,|$)" <<<"$subject"; then
  echo "Commit subject needs a type and a tracker ID first, e.g.:"
  echo "  feat(billing): M07 part payment"
  echo "  chore(ci): W08 add audit stage"
  echo "Got: $subject"
  exit 1
fi

if list=${LABRA_BANNED_TERMS:-$HOME/.config/labra/banned-terms.txt} && [[ -s $list ]] \
  && grep -vE '^\s*(#|$)' "$msg_file" | grep -qiF -f <(grep -vE '^\s*(#|$)' "$list"); then
  echo "Commit message contains a banned term (AGENTS.md rule 2)."
  exit 1
fi
