#!/bin/bash

die() {
  echo $*
  exit 1
}

if [ $# -lt 1 ] ; then
  echo "Usage: $0 try-syntax"
  cat <<EOF
-b do (debug and opt)
   [default is "do" if omitted]

-p linux,linux64,linux64-make,linux-make,linux-fuzz,linux64-fuzz,linux64-asan,linux64-fips,win64,win64-make,win,win-make,aarch64 (or "all" or "none")
   [default is "all" if omitted]

-u bogo,crmf,chains,cipher,db,ec,fips,gtest,interop,lowhash,merge,sdr,smime,tools,ssl (or "all" or "none")
   [default is "none" if omitted]

-t clang-format,scan-build,hacl,saw,coverage (or "all" or "none")
   [default is "none" if omitted]

-e all (or "none")
   [default is "none" if omitted]
EOF
  exit 1
fi

trysyntax="try: $*"

echo "Try syntax: "
echo " ${trysyntax}"
echo ""

echo "${trysyntax}" > "$(hg root)/.try"
hg add "$(hg root)/.try" || die "Couldn't add file $(hg root)/.try"
hg commit -m "${trysyntax}" "$(hg root)/.try" || die "Couldn't create the commit"

echo "Pushing ${trysyntax} to nss-try..."
hg push --new-branch -r . nss-try 

if [ $? -eq 0 ] ; then 
  rev=$(hg id --id)
  echo "Pushed ${rev} to Try. Find it on Treeherder:"
  echo ""
  echo "  https://treeherder.mozilla.org/#/jobs?repo=nss-try&revision=${rev}"
  echo ""
fi

echo "Cleaning up..."
hg strip -r .

if [ -e "$(hg root)/.try" ]; then
  die "Something went wrong! Watch out, $(hg root)/.try still exists."
fi
