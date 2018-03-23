#!/bin/bash

die() {
  echo "======= $@ ======="
  exit 1
}

checkDef=${1:-"check-def"}
bug=${2:-1445731}
dir=${3:-~/hg/mozilla-central}
cd $dir
hg purge . || die "Couldn't purge"
hg revert . || die "Couldn't revert"
hg up inbound || die "Couldn't update to inbound"
hg pull inbound -u || die "Couldn't pull from inbound"
hg bookmark nss-uplift -f || die "Couldn't make the nss-uplift bookmark"
# update NSS
tag=$(hg id https://hg.mozilla.org/projects/nss#default)
python2 client.py update_nss $tag || die "Couldn't update_nss"
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
echo hg push -r . inbound
echo hg bookmark -d nss-uplift
