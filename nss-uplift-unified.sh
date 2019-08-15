#!/bin/bash

die() {
  echo "======= $@ ======="
  exit 1
}

config_help() {
  echo "There's a problem in your ~/.nss-uplift.conf file. As a starting point, here are some defaults:"
  echo ""
  echo 'echo bug=1501587 > ~/.nss-uplift.conf'
  echo 'echo central_path=~/hg/mozilla-central >> ~/.nss-uplift.conf'
  echo 'echo nss_path=~/hg/nss >> ~/.nss-uplift.conf'
  echo 'echo check_def=true >> ~/.nss-uplift.conf'
  echo 'echo mozilla_branch=central >> ~/.nss-uplift.conf'
  echo 'echo reviewers=nssteam >> ~/.nss-uplift.conf'
  echo ""
}

if [ -r ~/.nss-uplift.conf ]; then
  . ~/.nss-uplift.conf
else
  config_help
  die "No configuration ready"
fi

# Don't build. TODO: Move into the nss-uplift.conf or add a flag
nobuild=${NOBUILD:-false}

tag=${1:-$(hg id https://hg.mozilla.org/projects/nss#default)}

echo "Usage: ${0} {NSS tag}"
echo
echo "Bug #: ${bug} https://bugzil.la/${bug}"

hash http 2>/dev/null || die "httpie not installed"
hash jq 2>/dev/null || die "jq not installed"
hash xpcshell 2>/dev/null || die "xpcshell not installed"
hash ssh-add 2>/dev/null || die "ssh-add not installed"

[ -r ${nss_path}/lib/util/nssutil.h ] ||
  die "nss_path ${nss_path} doesn't contain NSS; check ~/.nss-uplift.conf"
[ -r ${central_path}/security/nss/lib/util/nssutil.h ] ||
  die "central_path {central_path} doesn't contain mozilla-central; check ~/.nss-uplift.conf"

cd ${central_path}

if [ "${mozilla_branch}" == "" ] ; then
  config_help
  die "You must set a mozilla_branch in your conf."
fi
hg fxheads -T '{label("log.tag", join(fxheads, " "))}\n' | grep ${mozilla_branch} 2>&1 >/dev/null ||
  die "mozilla_branch path ${mozilla_branch} in ${central_path} doesn't appear to exist."

[ $(ssh-add -l|wc -l) -gt 1 ] || die "ssh keys not available, perhaps you need to ssh-add or shell in a different way?"

bugdata=$(http "https://bugzilla.mozilla.org/rest/bug/${bug}")
echo ${bugdata}| jq '{"Summary": .bugs[0].summary, "Status": .bugs[0].status}'

if [ "$(echo ${bugdata} | jq --raw-output '.bugs[0].status')" == "RESOLVED" ] ;then
  die "Bug is resolved. Please update ~/.nss-uplift.conf"
fi

if [ "$(echo ${bugdata} | jq --raw-output '.bugs[0].keywords | contains(["leave-open"])')" != "true" ] ;then
  die "Bug is not leave-open. Please update the bug."
fi

revset="reverse($(cat ${central_path}/security/nss/TAG-INFO)~-1::${tag})"

echo "Mozilla repo: ${central_path}"
echo "Mozilla branch: ${mozilla_branch}"
echo "NSS repo: ${nss_path}"
echo "NSS tag: ${tag}"
echo "Check-def: ${check_def}"
echo "Revset: ${revset}"
echo "Reviewers: ${reviewers}"
${nobuild} && echo "Not building (NOBUILD set)"

echo
echo "Press ctrl-c to cancel"
read cancel

pushd ${nss_path}
commitmsg=$(mktemp --tmpdir uplift_commit_msgXXXXX)
echo "Bug ${bug} - land NSS ${tag} UPGRADE_NSS_RELEASE, r=${reviewers}" > ${commitmsg}
echo "" >> ${commitmsg}
echo "Revset: ${revset}" >> ${commitmsg}
echo "" >> ${commitmsg}
hg log -T changelog -r "${revset}" >> ${commitmsg}
popd

less ${commitmsg}

if [ "${tag}" != "$(cat ${central_path}/security/nss/TAG-INFO)" ] ; then
  echo "Updating mozilla-unified repository to the current state of ${mozilla_branch}."

  hg purge . || die "Couldn't purge"
  hg revert . || die "Couldn't revert"
  hg pull ${mozilla_branch} || die "Couldn't pull from ${mozilla_branch}"
  hg up ${mozilla_branch} || die "Couldn't update to ${mozilla_branch}"

  if [ "${tag}" == "$(cat ${central_path}/security/nss/TAG-INFO)" ] ; then
    echo "NSS tag ${tag} is already landed in this repository."
    exit 1
  fi

  hg bookmark nss-uplift -f || die "Couldn't make the nss-uplift bookmark"

  # update NSS
  echo "Updating nss repository to the current state of default."
  cd ${nss_path}
  hg pull default

  cd ${central_path}

  ./mach python client.py update_nss --repo ${nss_path} $tag || die "Couldn't update_nss"

  # Check if there's a change in a .def file.
  # We might have to change security/nss.symbols then manually.
  defChanges=$(hg diff . | grep "\.def")
  if [ ! -z "${defChanges}" -a "${defChanges}" != " " -a "${check_def}" == "true" ]; then
    echo "Changes in .def. We might have to change security/nss.symbols then manually";
    exit 1
  fi
fi

origChanges=$(hg status | grep "\.orig")
if [ ! -z "${origChanges}" -a "${origChanges}" != " " ]; then
  echo "Some .orig files appear to be included. Those are probably not desirable.";
  exit 1
fi

if hg log -l 1 --template "{desc|firstline}\n" | grep ${tag} ; then
  echo "Looks like the commit was already made."
  echo "Updating to current ${mozilla_branch}..."
  hg pull ${mozilla_branch} && hg rebase -s nss-uplift -d ${mozilla_branch}
  ${nobuild} || ./mach build || die "Build failed! Manual intervention necessary!"

else
  ${nobuild} || ./mach build || die "Build failed! Manual intervention necessary!"

  # update CA telemetry hash table
  pushd security/manager/tools/
  xpcshell genRootCAHashes.js ${PWD}/../ssl/RootHashes.inc || die "Updating CA table failed! Manual intervention necessary!"
  popd


  hg addremove
  hg commit --logfile "${commitmsg}"


  # get everything that happened in the meantime
  hg up ${mozilla_branch}
  hg pull ${mozilla_branch} -u
  hg rebase -s nss-uplift -d ${mozilla_branch}
  hg up nss-uplift
fi

rm ${commitmsg}

VMINOR="$(grep NSSUTIL_VMINOR security/nss/lib/util/nssutil.h | cut --delim=' ' -f 3)"
if ! grep "AM_PATH_NSS(3.${VMINOR}" old-configure.in ; then
  echo "old-configure.in is out-of-date for this release. Fix it, then hg commit --amend and re-run"
  exit 1
fi

hg export -r .

read -n 1 -p "Do you wish to submit to try (y/n)? " try
case ${try} in
  y|Y ) ./mach try syntax -b "do" -p "all" -u "all" -t "none" ;;
  * ) ;;
esac

echo "=> PUSH"
echo "cd ${central_path}"
echo "hg pull ${mozilla_branch} && hg rebase -s nss-uplift -d ${mozilla_branch}"
echo "hg push -r . ${mozilla_branch}"

echo "=> Cleanup"
echo "hg bookmark -d nss-uplift"
