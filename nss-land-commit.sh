#!/bin/bash

errCount=0

warn() {
  echo "WARNING: $@"
  errCount=$((${errCount} + 1))
}

die() {
  echo "ERROR: $@"
  exit 1
}

hash http 2>/dev/null || die "httpie not installed"
hash jq 2>/dev/null || die "jq not installed"

revision=${1:-.}

outgoingData=$(hg outgoing -r ${revision} --template json | tail -n +3)
if [[ "${outgoingData}" == "no changes found" ]]; then
  echo ${outgoingData}
  exit 0
fi
patches=$(echo ${outgoingData} | jq '[.[].desc | {bug: [capture("[Bb]ug (?<bug>[0-9]+)"), capture(" (?<reviewers>r[?=].*)+"), {headline:.|split("\n")[0]}, {body:.|split("\n")}] }|flatten|add]')

echo "Stack of commits:"

for bug in $(echo ${patches} | jq --raw-output '.[].bug'); do
  bugData=$(http "https://bugzilla.mozilla.org/rest/bug/${bug}")
  patchData=$(echo ${patches}| jq ".[] | select(.bug==\"${bug}\")")

  echo "Bug #${bug}"
  echo ${patchData} | jq '.'
  echo ${bugData}| jq '{"Id": .bugs[0].id, "Summary": .bugs[0].summary, "Status": .bugs[0].status}'
  echo ""

  if [[ $(echo ${patchData} | jq '.reviewers|test("r=.+")') == "false" ]] ; then
    warn "Bug ${bug} has no r= noted"
  fi

  if [[ $(echo ${patchData} | jq '.reviewers|test("r\\?")') == "true" ]] ; then
    warn "Bug ${bug} has an r? noted"
  fi

  status="$(echo ${bugData} | jq --raw-output '.bugs[0].status')"
  if [[ "${status}" != "NEW" ]] && [[ "${status}" != "ASSIGNED" ]] ; then
    warn "Bug ${bug} is in an odd state. May not be the right bug?"
  fi

  if [[ $(echo ${patchData} | jq '.body|join("")|contains("Differential Revision: https")') == "false" ]] ; then
    warn "Bug ${bug} is missing a Differential Revision note "
  fi


  echo "==============="
done

if [[ ${errCount} -gt 0 ]]; then
  echo "${errCount} warnings!"
  exit 1
fi

while true; do
    read -p "OK, looks alright. Ready to push?" yn
    case $yn in
        [Yy]* ) echo hg push -r ${revision}; break;;
        [Nn]* ) exit;;
        * ) echo "Please answer yes or no.";;
    esac
done
