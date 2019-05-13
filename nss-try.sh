#!/bin/bash

die() {
  echo "$@"
  exit 1
}

[[ $(hg status -mard | wc -l) -eq 0 ]] || \
    die "Please commit unstaged changes"

if [ $# -lt 1 ] ; then
  echo "Usage: $0 try-syntax"
  cat <<EOF
-b do (d=debug, o=opt)
   [default is "do" if omitted]

-p linux64,linux64-make,linux64-fuzz,linux64-asan,linux64-fips,linux,linux-make,linux-fuzz,
   aarch64,mac,win64,win64-make,win,win-make (or "all" or "none")
   [default is "all" if omitted]

-u bogo,crmf,chains,cipher,db,ec,fips,gtest,interop,lowhash,merge,sdr,smime,ssl,tlsfuzzer,
   tools (or "all" or "none")
   [default is "none" if omitted]

-t abi,clang-format,coverage,hacl,saw,scan-build (or "all" or "none")
   [default is "none" if omitted]

-e all (or "none")
   [default is "none" if omitted]
EOF
  exit 1
fi

trysyntax="try: $*"

echo "Try syntax: "
echo "  ${trysyntax}"
echo ""

tryfile="$(hg root)/.try"
echo "${trysyntax}" > "$tryfile"
hg add "$tryfile"  || die "Couldn't add file $tryfile"
hg commit -m "${trysyntax}" "$tryfile"
# || die "Couldn't create the commit"

echo "Pushing to nss-try..."
if hg push --new-branch -r . nss-try; then
  rev=$(hg id --id)
  echo "Pushed ${rev} to nss-try. Find it on Treeherder:"
  echo ""
  echo "  https://treeherder.mozilla.org/#/jobs?repo=nss-try&revision=${rev}"
  echo ""
fi

echo "Cleaning up..."
hg strip -r .

[[ -e "$tryfile" ]] && \
  die "Something went wrong! Watch out, $tryfile still exists."
