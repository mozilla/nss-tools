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

reset_dir() {
  if hg id | grep nss-uplift; then
    hg strip -r nss-uplift
  fi
  hg revert -C -a -i
  rm -f ${commitmsg}
}

if [ -r ~/.nss-uplift.conf ]; then
  . ~/.nss-uplift.conf
else
  config_help
  die "No configuration ready"
fi

# Don't build. TODO: Move into the nss-uplift.conf or add a flag
nobuild=${NOBUILD:-false}
nohashes=${NOHASHES:-false}
securitybug=${SECURITY:-false}

tag=${1:-$(hg id https://hg.mozilla.org/projects/nss#default)}

echo "Usage: ${0} {NSS tag}"
echo
if [ "x${bug}" != "x" ] ; then
  echo "Bug #: ${bug} https://bugzil.la/${bug}"
fi

hash http 2>/dev/null || die "httpie not installed"
hash jq 2>/dev/null || die "jq not installed"
hash xpcshell 2>/dev/null || die "xpcshell not installed"
hash ssh-add 2>/dev/null || die "ssh-add not installed"
hash moz-phab 2>/dev/null || die "moz-phab not installed"

pip3 install mozphab --user --upgrade

[ -r ${nss_path}/lib/util/nssutil.h ] ||
  die "nss_path ${nss_path} doesn't contain NSS; check ~/.nss-uplift.conf"
[ -r ${central_path}/security/nss/lib/util/nssutil.h ] ||
  die "central_path ${central_path} doesn't contain NSS; check ~/.nss-uplift.conf"

cd ${central_path}

if [ "${mozilla_branch}" == "" ] ; then
  config_help
  die "You must set a mozilla_branch in your conf."
fi
hg fxheads -T '{label("log.tag", join(fxheads, " "))}\n' | grep ${mozilla_branch} 2>&1 >/dev/null ||
  die "mozilla_branch path ${mozilla_branch} in ${central_path} doesn't appear to exist."

[ $(ssh-add -l|wc -l) -ge 1 ] || die "ssh keys not available, perhaps you need to ssh-add or shell in a different way?"

if [ "x${bug}" != "x" ] && [ ${securitybug} = false ] ; then
  bugdata=$(http "https://bugzilla.mozilla.org/rest/bug/${bug}")
  echo ${bugdata}| jq '{"Summary": .bugs[0].summary, "Status": .bugs[0].status}'

  if [ "$(echo ${bugdata} | jq --raw-output '.bugs[0].status')" == "RESOLVED" ] ;then
    die "Bug is resolved. Please update ~/.nss-uplift.conf"
  fi

  if [ "$(echo ${bugdata} | jq --raw-output '.bugs[0].keywords | contains(["leave-open"])')" != "true" ] ;then
    die "Bug is not leave-open. Please update the bug."
  fi
fi

if [ "${tag}" == "$(cat ${central_path}/security/nss/TAG-INFO)" ] ; then
  read -n 1 -p "Uplift appears to be in progress. Clear, or resume? [C/r]? " try
  case ${try} in
    r|R) ;;
    *) reset_dir ;;
  esac
fi

if [ "${tag}" != "$(cat ${central_path}/security/nss/TAG-INFO)" ] ; then
  echo "Updating mozilla-unified repository to the current state of ${mozilla_branch}."

  hg purge --all . || die "Couldn't purge"
  hg revert -q -C --all || die "Couldn't revert"
  hg pull ${mozilla_branch} || die "Couldn't pull from ${mozilla_branch}"
  hg up ${mozilla_branch} || die "Couldn't update to ${mozilla_branch}"

  if [ "${tag}" == "$(cat ${central_path}/security/nss/TAG-INFO)" ] ; then
    echo "NSS tag ${tag} is already landed in this repository."
    exit 1
  fi
fi

revset="${REVSET:-reverse($(cat ${central_path}/security/nss/TAG-INFO)~-1::${tag})}"

echo "Mozilla repo: ${central_path}"
echo "Mozilla branch: ${mozilla_branch}"
echo "NSS repo: ${nss_path}"
echo "NSS tag: ${tag}"
echo "Check-def: ${check_def}"
echo "Revset: ${revset}"
echo "Reviewers: ${reviewers}"
${nobuild} && echo "Not building (NOBUILD set)"
${nohashes} && echo "Not recreating CA hashes (NOHASHES set)"
${securitybug} && echo "SECURITY BUG"

echo
echo "Press ctrl-c to cancel"
read cancel

pushd ${nss_path}
# update NSS
echo "Updating nss repository to the current state of default."
hg pull default

commitmsg=/tmp/${tag}.commitmsg
if [ ! -r "${commitmsg}" ] ; then
  echo "Bug ${bug:-unknown} - land NSS ${tag} UPGRADE_NSS_RELEASE, r=${reviewers}" > ${commitmsg}
  echo "" >> ${commitmsg}
  hg log -T changelog -r "${revset}" | grep -vE "(phabricator.services.mozilla.com|Differential)" >> ${commitmsg}
fi
popd

less ${commitmsg}

if [ "${tag}" != "$(cat ${central_path}/security/nss/TAG-INFO)" ] ; then
  hg bookmark nss-uplift -f || die "Couldn't make the nss-uplift bookmark"

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
  ${nohashes} || xpcshell genRootCAHashes.js ${PWD}/../ssl/RootHashes.inc || die "Updating CA table failed! Manual intervention necessary!"
  popd

  hg addremove
  hg commit --logfile "${commitmsg}"
fi

rm -f ${commitmsg}

VMINOR="$(grep NSSUTIL_VMINOR security/nss/lib/util/nssutil.h | awk '{print $3}')"
if ! grep "nss >= 3.${VMINOR}" build/moz.configure/nss.configure ; then
  echo "build/moz.configure/nss.configure is out-of-date for this release. Fix it, then hg commit --amend and re-run"
  exit 1
fi

hg export -r .

read -n 1 -p "Do you wish to submit to try (y/n)? " try
case ${try} in
  y|Y ) ./mach try syntax -b "do" -p "all" -u "all" -t "none" ;;
  * ) ;;
esac
echo ""

echo "Enter to continue"
read next

read -n 1 -p "Do you wish to submit to Phabricator (y/n)? " phab
case ${phab} in
  y|Y ) moz-phab submit --reviewers ${reviewers} nss-uplift ;;
  * ) ;;
esac
echo ""
