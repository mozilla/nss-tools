#!/bin/bash

die() {
  echo "======= $@ ======="
  exit 1
}

if [ -r ~/.nss-uplift.conf ]; then
 . ~/.nss-uplift.conf
else
 echo "You need a ~/.nss-uplift.conf file. As a starting point, here are some defaults:"
 echo ""
 echo 'echo bug="1501587" > ~/.nss-uplift.conf'
 echo 'echo central_path="~/hg/mozilla-central" >> ~/.nss-uplift.conf'
 echo 'echo check_def="true" >> ~/.nss-uplift.conf'
 echo ""
 die "No configuration ready"
fi

tag=${1:-$(hg id https://hg.mozilla.org/projects/nss#default)}

echo "Usage: ${0} {NSS tag}"
echo
echo "Bug #: ${bug} https://bugzil.la/${bug}"

hash http 2>/dev/null || die "httpie not installed"
hash jq 2>/dev/null || die "jq not installed"
hash xpcshell 2>/dev/null || die "xpcshell not installed"
hash ssh-add 2>/dev/null || die "ssh-add not installed"

[ $(ssh-add -l|wc -l) -gt 1 ] || die "ssh keys not available, perhaps you need to ssh-add or shell in a different way?"

http "https://bugzilla.mozilla.org/rest/bug/${bug}" | jq '{"Summary": .bugs[0].summary, "Status": .bugs[0].status}'

echo "Mozilla repo: ${central_path}"
echo "NSS tag: ${tag}"
echo "Check-def: ${check_def}"
echo
echo "Press ctrl-c to cancel."
read cancel

echo "Updating to the current state of inbound."
cd ${central_path}

hg purge . || die "Couldn't purge"
hg revert . || die "Couldn't revert"
hg pull inbound || die "Couldn't pull from inbound"
hg up inbound || die "Couldn't update to inbound"
#hg pull inbound -u || die "Couldn't pull from inbound"

if [ "${tag}" == "$(cat ${central_path}/security/nss/TAG-INFO)" ] ; then
  echo "NSS tag ${tag} is already landed in this repository."
  exit 1
fi

hg bookmark nss-uplift -f || die "Couldn't make the nss-uplift bookmark"
# update NSS
./mach python client.py update_nss $tag || die "Couldn't update_nss"
# Check if there's a change in a .def file.
# We might have to change security/nss.symbols then manually.
defChanges=$(hg diff . | grep "\.def")
if [ ! -z "${defChanges}" -a "${defChanges}" != " " -a "${check_def}" == "true" ]; then
  echo "Changes in .def. We might have to change security/nss.symbols then manually";
  exit 1
fi
# build
./mach build || die "Build failed! Manual intervention necessary!"

# update CA telemetry hash table
pushd security/manager/tools/
xpcshell genRootCAHashes.js ${PWD}/../ssl/RootHashes.inc || die "Updating CA table failed! Manual intervention necessary!"
popd

origChanges=$(hg status | grep "\.orig")
if [ ! -z "${origChanges}" -a "${origChanges}" != " " ]; then
  echo "Some .orig files appear to be included. Those are probably not desirable.";
  exit 1
fi

hg addremove
hg commit -m "Bug ${bug} - land NSS ${tag} UPGRADE_NSS_RELEASE, r=me"
# get everything that happened in the meantime
hg up inbound
hg pull inbound -u
hg rebase -s nss-uplift -d inbound
hg up nss-uplift


read -n 1 -p "Do you wish to submit to try (y/n)? " try
case ${try} in
  y|Y ) ./mach try syntax -b "do" -p "all" -u "all" -t "none" ;;
  * ) ;;
esac

echo "=> PUSH"
echo "cd ${central_path}"
echo "hg pull inbound && hg rebase -s nss-uplift -d inbound"
echo "hg push -r . inbound"

echo "=> Cleanup"
echo "hg bookmark -d nss-uplift"
