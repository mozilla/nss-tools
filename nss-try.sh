#!/bin/bash

die() {
  echo "$@"
  exit 1
}

[[ $(hg status -mard | wc -l) -eq 0 ]] || \
    die "Please commit unstaged changes"

if ! hg path nss-try | grep hg.mozilla.org/projects/nss-try > /dev/null ; then
  die "You need to set up the nss-try path. See https://wiki.mozilla.org/NSS:TryServer"
fi

if [ $# -lt 1 ] ; then
  echo "Usage: $0 try-syntax"
  cat <<EOF
-b d | o
   Description: Specifies the type of build to perform, where d=debug and o=opt.
   Default: do

-p linux64,linux64-make,linux64-fuzz,linux64-asan,linux64-fips,linux,linux-make,linux-fuzz,
   aarch64,mac,win64,win64-make,win,win-make | all | none
   Description: Specify which platforms to enable. Valid options are any subset (for
                example: '-p mac,win64'), "all", or "none".
   Default: all

-u bogo,crmf,chains,cipher,db,ec,fips,gtest,interop,lowhash,merge,mpi,sdr,smime,ssl,tlsfuzzer,
   tools | all | none
   Description: Specify a subset of tests to run, "all", or "none". Any required parent
                tasks (such as generating certificates) may also run.
   Default: none

-t abi,clang-format,coverage,coverity,hacl,saw,scan-build | all | none
   Description: Specify any subset of tools, "all", or "none".
   Default: none

-e all | none
   Description: Specify "all" or "none" to enable or disable extra builds. These include old
                compiler versions and modular makefile builds.
   Default: none

--nspr-patch
   Description: If specified, causes each target to apply a patch against NSPR prior to building
                and running any tests. The patch should be the output of "hg diff" and must be
                saved as "nspr.patch" in the top nss/ directory.
   Default: Not specified

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
hg commit -m "${trysyntax} ${COMMIT_SUFFIX}" "$tryfile"
# || die "Couldn't create the commit"

echo "Pushing to nss-try..."
if hg push --new-branch --force -r . nss-try; then
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
