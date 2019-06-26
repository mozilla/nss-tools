#!/bin/sh
if [[ -z "$NSS_DIR" ]]; then
    NSS_DIR=$(hg root 2>/dev/null || git rev-parse --show-toplevel 2>/dev/null)
fi
if [[ ! -d "$NSS_DIR" ]]; then
    echo "Can't find NSS directory.  Set \$NSS_DIR." 1>&2
    exit 2
fi
root=$(cd "$NSS_DIR/.."; pwd -P)
filter=()
filter_excl=()
build=
debug=
valgrind=
rr=
args=()
shuffle=
verbose=
help=
slow_tests=( \
    "*.AlertBeforeServerHello/*" \
    "*.ConnectWithExpiredTicket*" \
    "*.HrrThenRemoveKeyShare/1" \
    "*.HrrThenRemoveSignatureAlgorithms/1" \
    "*.HrrThenRemoveSupportedGroups/1" \
    "*.KeyLogFile/*" \
    "*.ReplaceFirstClientRecordWithApplicationData/*" \
    "*.ReplaceFirstServerRecordWithApplicationData/*" \
    "*.RetryCookieEmpty/1" \
    "*.RetryCookieWithExtras/1" \
    "*.RetryStatefulDropCookie/1" \
    "*.ServerAuthBiggestRsa/*" \
    "*.WeakDHGroup/*" \
    "*/TlsCipherSuiteTest.*" \
    "*/TlsSignatureSchemeConfiguration.*" \
    "DatagramDrop13/*" \
    "DatagramPre13/TlsConnectDatagramPre13.*" \
    "TLSVersionRanges/*" \
    "TlsConnectDatagram13.AuthCompleteBeforeFinished" \
    "TlsConnectStreamTls13.TimePassesByDefault" \
)
while [ $# -ge 1 ]; do
    case "$1" in
        -b) build=1 ;;
        -d) debug=1 ;;
	-f) filter_excl+=("${slow_tests[@]}") ;;
        -r) rr=1 ;;
        -s) args+=(--gtest_shuffle) ;;
        -g) valgrind=1 ;;
        -v) args+=(-v);verbose=1 ;;
        -l) args+=(--gtest_list_tests) ;;
        -t) export SSLTRACE="$2"; shift ;;
        -h|--help)
            echo "$0 [-b|-d|-r|-l|-h] [-v] [-s] [-t <n>] [[-]filter...]" 1>&2
            echo 1>&2
            echo "  Run ssl_gtests." 1>&2
            echo 1>&2
            echo "    -b        Build first (only uses default options)" 1>&2
            echo "    -d        Run in debugger" 1>&2
            echo "    -f        Disable slow tests" 1>&2
            echo "    -r        Run with record and replay" 1>&2
            echo "    -g        Run under valgrind" 1>&2
            echo "    -l        List tests" 1>&2
            echo "    -h        Show this help" 1>&2
            echo "    -s        Shuffle test order" 1>&2
            echo "    -v        Verbose output" 1>&2
            echo "    -t <n>    Set SSLTRACE=<n>" 1>&2
            echo "    <filter>  Include tests with a names matching '*<filter>*'" 1>&2
            echo "    -<filter> Exclude tests with a names matching '*<filter>*'" 1>&2
            echo 1>&2
            echo "    --gtest_* Pass argument to gtest ..." 1>&2
            echo 1>&2

            args=(--help)
            ;;
        --gtest_*) args+=("$1") ;;
        *)
            if [ "${1#-}" = "$1" ]; then
                filter+=("*$1*")
            else
                filter_excl+=("*${1#-}*")
            fi
            ;;
    esac
    shift
done

if [[ "$build" = 1 ]]; then
    ~/code/nss/build.sh || exit 1
fi

dist="$root/dist/$(cat "$root/dist/latest")"
if [[ $(uname -s) = "Darwin" ]]; then
    export DYLD_LIBRARY_PATH="$dist/lib:$DYLD_LIBRARY_PATH"
    debugger=(/Applications/Xcode.app/Contents/Developer/usr/bin/lldb --)
else
    export LD_LIBRARY_PATH="$dist/lib:$LD_LIBRARY_PATH"
    debugger=(gdb -ex run --args)
fi
export NSS_STRICT_SHUTDOWN=1
args+=("--gtest_filter="$(IFS=:;echo -n "${filter[*]:-*}";[[ "${#filter_excl[@]}" -gt 0 ]] && echo -n ":-${filter_excl[*]}"))
db=
for d in $(find "$root/tests_results" -name ssl_gtests -print); do
    [ -z "$db" ] && db="$d"
    [ "$d" -nt "$db" ] && db="$d"
done
prog=($dist/bin/ssl_gtest -d "$db" "${args[@]}")
if [[ "$verbose" = 1 ]]; then
    echo "Run: ${prog[*]}" 1>&2
fi
if [[ "$debug" = 1 ]]; then
    exec "${debugger[@]}" "${prog[@]}"
elif [[ "$rr" = 1 ]]; then
    rr -S record -n "${prog[@]}"
    exec rr -S replay
elif [[ "$valgrind" = 1 ]]; then
    exec valgrind "${prog[@]}"
else
    exec "${prog[@]}"
fi
