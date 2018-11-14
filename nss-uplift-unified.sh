#!/bin/bash

die() {
  echo "======= $@ ======="
  exit 1
}

bug=${1:-1501587}
tag=${2:-$(hg id https://hg.mozilla.org/projects/nss#default)}
checkDef=${3:-"check-def"}
dir=${4:-~/hg/mozilla-central}

echo "Usage: $0 [bug #] [NSS tag] [check-def] [m-c dir]"
echo
echo "Check-def: ${checkDef}"
echo "Bug #: ${bug} https://bugzil.la/${bug}"

if [ -x $(which http) ] && [ -x $(which jq) ] ; then
  http "https://bugzilla.mozilla.org/rest/bug/${bug}" | jq '{"Summary": .bugs[0].summary, "Status": .bugs[0].status}'
fi

echo "Mozilla repo: ${dir}"
echo "NSS tag: ${tag}"
echo
echo "Press ctrl-c to cancel."
read cancel

echo "Updating to the current state of inbound."
cd $dir
hg purge . || die "Couldn't purge"
hg revert . || die "Couldn't revert"
hg up inbound || die "Couldn't update to inbound"
hg pull inbound -u || die "Couldn't pull from inbound"

if [ "${tag}" == "$(cat ${dir}/security/nss/TAG-INFO)" ] ; then
  echo "NSS tag ${tag} is already landed in this repository."
  exit 1
fi

hg bookmark nss-uplift -f || die "Couldn't make the nss-uplift bookmark"
# update NSS
mach python client.py update_nss $tag || die "Couldn't update_nss"
# Check if there's a change in a .def file.
# We might have to change security/nss.symbols then manually.
defChanges=$(hg diff . | grep "\.def")
if [ ! -z "$defChanges" -a "$defChanges" != " " -a "$checkDef" == "check-def" ]; then
  echo "Changes in .def. We might have to change security/nss.symbols then manually";
  exit 1
fi
# build
./mach build || die "Build failed! Manual intervention necessary!"

# update CA telemetry hash table
pushd security/manager/tools/
xpcshell genRootCAHashes.js $PWD/../ssl/RootHashes.inc || die "Updating CA table failed! Manual intervention necessary!"
popd

origChanges=$(hg status | grep "\.orig")
if [ ! -z "$origChanges" -a "$origChanges" != " " ]; then
  echo "Some .orig files appear to be included. Those are probably not desirable.";
  exit 1
fi

hg addremove
hg commit -m "Bug $bug - land NSS $tag UPGRADE_NSS_RELEASE, r=me"
# get everything that happened in the meantime
hg up inbound
hg pull inbound -u
hg rebase -s nss-uplift -d inbound
hg up nss-uplift

echo "=> Try"
./mach try syntax -b "do" -p "all" -u "all" -t "none"

echo "=> PUSH"
echo hg pull inbound
echo hg rebase -s nss-uplift -d inbound
echo hg push -r . inbound

echo "=> Cleanup"
echo hg bookmark -d nss-uplift
