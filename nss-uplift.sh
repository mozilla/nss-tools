#!/bin/bash

checkDef=${1:-"check-def"}
bug=${2:-1432177}
dir=${3:-/home/franziskus/Code/automation/mozilla-inbound}
cd $dir
hg purge .
hg revert .
hg up default-tip
hg pull -u
hg book nss-uplift -f
# update NSS
tag=$(hg id https://hg.mozilla.org/projects/nss#default)
python2 client.py update_nss $tag
# Check if there's a change in a .def file.
# We might have to change security/nss.symbols then manually.
defChanges=$(hg diff . | grep "\.def")
if [ ! -z "$defChanges" -a "$defChanges" != " " -a "$checkDef" == "check-def" ]; then
  echo "Changes in .def. We might have to change security/nss.symbols then manually";
  exit 1
fi
# build
./mach build
if [ $? -ne 0 ]; then
  echo "======= Build failed! Manual intervention necessary! ======="
  exit 1
fi
# update CA telemetry hash table
cd security/manager/tools/
LD_LIBRARY_PATH=../../../obj-x86_64-pc-linux-gnu/dist/bin/ ../../../obj-x86_64-pc-linux-gnu/dist/bin/xpcshell genRootCAHashes.js $PWD/../ssl/RootHashes.inc
if [ $? -ne 0 ]; then
  echo "======= Updating CA table failed! Manual intervention necessary! ======="
  exit 1
fi
cd -
hg addremove
hg commit -m "Bug $bug - land NSS $tag UPGRADE_NSS_RELEASE, r=me"
# get everything that happened in the meantime
hg up default-tip
hg pull -u
hg up nss-uplift
hg rebase -d default-tip
hg book -d nss-uplift
echo "=> PUSH"
# hg push -r .
