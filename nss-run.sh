#!/usr/bin/env bash
root=$(cd "$NSS_DIR/.."; pwd -P)
dist="$root/dist/$(cat "$root/dist/latest")"

debug=()
while [[ "${1:0:1}" == "-" ]]; do
    case "$1" in
    --complete) exec find "$dist/bin" -maxdepth 1 -type f -executable -printf '%P\n' ;;
    --print-completion)
        cat << 'EOC'
_nss_run_complete() {
  cmds=($("${COMP_WORDS[0]}" --complete))
  i=1
  while [[ ${#COMP_WORDS[@]} -gt $i && "${COMP_WORDS[i]:0:1}" = "-" ]]; do
    i=$(($i + 1))
  done
  if [[ $COMP_CWORD -eq $i ]]; then
    COMPREPLY=($(compgen -W "${cmds[*]}" -- "${COMP_WORDS[COMP_CWORD]}"))
  fi
  return 0
}
EOC
        barecmd="${0##*/}"
        echo 'complete -o default -F _nss_run_complete' "${barecmd@Q}" "${0@Q}"
        exit
        ;;
    -d)
        if [[ "$(uname -s)" == "Darwin" ]]; then
            debug=(/Applications/Xcode.app/Contents/Developer/usr/bin/lldb --)
        else
            debug=(gdb --args)
        fi
        ;;
    -t) shift; export SSLTRACE="$1" ;;
    -h|--help) shift $# ;;
    esac
    shift
done

if [[ $# -eq 0 ]]; then
    echo "Usage: $0 [-d] [-t <n>] <nss-cmd> [args ...]" 1>&2
    echo 1>&2
    echo "    -d Debug the command" 1>&2
    echo "    -t Enable SSL tracing" 1>&2
    echo 1>&2
    echo "    Enable completion (bash) with:" 1>&2
    echo "    $ source <($0 --print-completion)" 1>&2
    exit 2
fi

if [[ "$(uname -s)" == "Darwin" ]]; then
    export DYLD_LIBRARY_PATH="$dist/lib:$DYLD_LIBRARY_PATH"
else
    export LD_LIBRARY_PATH="$dist"/lib:"$LD_LIBRARY_PATH"
fi
bin="$dist"/bin/"$1"
if [[ ! -x "$bin" ]]; then
    echo "Not found: $1" 1>&2
    exit 1
fi
shift
exec "${debug[@]}" "$bin" "$@"
