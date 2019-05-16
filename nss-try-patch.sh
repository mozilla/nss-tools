#!/bin/bash

die() {
  echo "$@"
  exit 1
}

usage() {
  echo "$0 Dxxxx <try syntax>"
}

if [ $# -lt 1 ] ; then
  usage
  exit 1
fi

if [ $# -lt 2 ] ; then
  usage
  echo ""
  echo "Try Syntax:"
  echo ""
  $(dirname $0)/nss-try.sh | tail -n+2
  exit 1
fi

hash moz-phab || die "moz-phab not found"

differential_id=$1
shift
try_syntax=$@

moz-phab patch --apply-to here ${differential_id} || die "Couldn't download patch ${differential_id}"

hg export -r .

echo "Proceed? ctrl-c to stop"
read check_proceed

$(dirname $0)/nss-try.sh ${try_syntax}

hg strip -r ${differential_id} || die "Couldn't strip off commit for bookmark ${differential_id}"
hg bookmark -d ${differential_id} || die "Couldn't clean up bookmark ${differential_id}"