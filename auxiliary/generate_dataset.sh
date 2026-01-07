#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2025 Simon A. F. Lund <os@safl.dk>
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Deterministic pseudo dataset generator (ImageFolder layout) using GNU parallel.
#
# Layout:
#   <path>/<class>/*.bin
#
# Each file contains pseudorandom binary content of an exact byte size,
# produced from /dev/zero via AES-256-CTR with a per-file raw key and IV
# (no KDF). The files are not real images.
#
# See ./generate_dataset.sh --help for usage and examples.
set -euo pipefail

function need() {
  command -v "$1" > /dev/null 2>&1 || {
    echo "Missing tool: $1" >&2
    exit 2
  }
}

# nounset-safe map: val -> [min,max]
function map_range() {
  local val=0 min=0 max=0 span=0 mod=0
  val=${1:?\$1(val) required}
  min=${2:?\$2(min) required}
  max=${3:?\$3(max) required}
  span=$((max - min + 1))
  ((span > 0)) || {
    echo "Bad range [$min,$max]" >&2
    exit 3
  }
  mod=$((val % span))
  ((mod < 0)) && mod=$((mod + span))
  echo $((mod + min))
}

# Write exactly nbytes via AES-256-CTR using raw hex key/iv (no KDF).
# Feed exactly nbytes into openssl; openssl writes the file itself.
function mkbytes_exact() {
  local out="${1:?\$1(out) required}" nbytes="${2:?\$2(nbytes) required}"
  local key_hex="${3:?\$3(key_hex) required}" iv_hex="${4:?\$4(iv_hex) required}"
  head -c "$nbytes" /dev/zero |
    openssl enc -aes-256-ctr -nosalt -K "$key_hex" -iv "$iv_hex" -out "$out"
}

# Generate files in index range [start, end] for given class/split.
# Per file we consume 13 PRNG steps: 1(size) + 8(key 256b) + 4(iv 128b).
# At the end, print a single "done" line for this batch.
function range_worker() {
  local cname="${1:?\$1(cname) required}"
  local start="${2:?\$2(start) required}"
  local end="${3:?\$3(end) required}"
  local class_seed="${4:?\$4(class_seed) required}"
  local filesize_min="${5:?\$5(filesize_min) required}"
  local filesize_max="${6:?\$6(filesize_max) required}"
  local root="${7:?\$7(root) required}"

  local t0
  t0=$(date +%s)

  local s="$class_seed" a=1664525 inc=1013904223 mask=$((0xFFFFFFFF))

  # Skip ahead to state before 'start'
  local steps_per_file=13
  local skip=$((steps_per_file * (start - 1)))
  for ((i = 0; i < skip; i++)); do
    s=$(((a * s + inc) & mask))
  done

  local idx nbytes v fname key_hex iv_hex
  for ((idx = start; idx <= end; idx++)); do
    # size (1 step)
    s=$(((a * s + inc) & mask))
    v="$s"
    nbytes=$(map_range "$v" "$filesize_min" "$filesize_max")

    # key 256-bit (8 steps of 32 bits)
    key_hex=""
    for _ in 1 2 3 4 5 6 7 8; do
      s=$(((a * s + inc) & mask))
      printf -v key_hex '%s%08x' "$key_hex" "$s"
    done

    # iv 128-bit (4 steps of 32 bits)
    iv_hex=""
    for _ in 1 2 3 4; do
      s=$(((a * s + inc) & mask))
      printf -v iv_hex '%s%08x' "$iv_hex" "$s"
    done

    fname="${cname}_$(printf "%08d" "$idx").bin"
    mkbytes_exact "${root}/${split}/${cname}/${fname}" "$nbytes" "$key_hex" "$iv_hex"
  done

  local t1
  t1=$(date +%s)
  local files_done=$((end - start + 1))
  local dur=$((t1 - t0))
  echo "done ${cname} ${split} ${start}-${end} (${files_done} files, ${dur}s)"
}

export -f map_range mkbytes_exact range_worker

function usage() {
  cat << 'EOF'
Usage:
  ./generate_dataset.sh --path DIR --nclasses N --nfiles-min N --nfiles-max N \
     --filesize-min BYTES --filesize-max BYTES --seed STR --jobs N

All arguments are required.

Example:
  ./generate_dataset.sh --path /data/pseudo --nclasses 1000 \
     --nfiles-min 1000 --nfiles-max 1300 \
     --filesize-min 70000 --filesize-max 160000 \
     --seed imagenetish --jobs $(nproc)
EOF
  exit 1
}

function main() {
  local ROOT="" NCLASSES="" NFILES_MIN="" NFILES_MAX="" FILESIZE_MIN="" FILESIZE_MAX="" SEED="" JOBS=""

  while (("$#")); do
    case "$1" in
    -p | --path)
      ROOT="${2:-}"
      shift 2
      ;;
    -n | --nclasses)
      NCLASSES="${2:-}"
      shift 2
      ;;
    --nfiles-min)
      NFILES_MIN="${2:-}"
      shift 2
      ;;
    --nfiles-max)
      NFILES_MAX="${2:-}"
      shift 2
      ;;
    --filesize-min)
      FILESIZE_MIN="${2:-}"
      shift 2
      ;;
    --filesize-max)
      FILESIZE_MAX="${2:-}"
      shift 2
      ;;
    -S | --seed | --seed=*)
      SEED="${2:-}"
      shift 2
      ;;
    -j | --jobs)
      JOBS="${2:-}"
      shift 2
      ;;
    -h | --help) usage ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      ;;
    esac
  done

  [[ -n "$ROOT" && -n "$NCLASSES" && -n "$NFILES_MIN" && -n "$NFILES_MAX" &&
    -n "$FILESIZE_MIN" && -n "$FILESIZE_MAX" && -n "$SEED" && -n "$JOBS" ]] || usage

  for t in openssl head cksum mkdir parallel; do need "$t"; done

  echo "Root: $ROOT"
  echo "Classes: $NCLASSES"
  echo "Files/class: ${NFILES_MIN}..${NFILES_MAX}"
  echo "File size: ${FILESIZE_MIN}..${FILESIZE_MAX} bytes"
  echo "Seed: $SEED | Jobs: $JOBS"
  echo

  # First pass: per-class counts and total files
  local counts_file tasks_file
  counts_file="$(mktemp)"
  tasks_file="$(mktemp)"
  trap 'rm -f "${counts_file:-}" "${tasks_file:-}"' EXIT

  local total_files=0
  local c=0 cname="" class_seed="" n_total=0
  for ((c = 1; c <= NCLASSES; c++)); do
    cname="class$(printf "%03d" "$c")"
    class_seed="$(cksum <<< "${SEED}-${cname}")"
    class_seed="${class_seed%% *}"
    n_total=$(map_range "$class_seed" "$NFILES_MIN" "$NFILES_MAX")
    total_files=$((total_files + n_total))

    mkdir -p "$ROOT/$cname"
    printf "%s\t%s\t%d\n" "$cname" "$class_seed" "$n_total" >> "$counts_file"
  done

  # Auto-size batch size from jobs and total files (about 128 tasks per job)
  local batches=$((JOBS * 128))
  ((batches < 1)) && batches=1
  local batch_size=$(((total_files + batches - 1) / batches))
  ((batch_size < 1)) && batch_size=1

  echo "Total files: $total_files | Computed batch size: $batch_size (approx. $batches tasks)"
  echo

  # Build task list: cname split start end class_seed
  while IFS=$'\t' read -r cname class_seed n_total; do
    enqueue() {
      local n="${1:?\$1(n) required}"
      ((n <= 0)) && return 0
      local start=1 end=0
      while ((start <= n)); do
        end=$((start + batch_size - 1))
        ((end > n)) && end="$n"
        printf "%s\t%d\t%d\t%s\n" "$cname" "$start" "$end" "$class_seed" >> "$tasks_file"
        start=$((end + 1))
      done
    }
    enqueue "$n_total"
  done < "$counts_file"

  # Build GNU parallel options, add --bar only when stdout is a TTY
  local PAR_OPTS=(--colsep $'\t' -j "$JOBS" --line-buffer "--halt=soon,fail=1")
  if [ -t 1 ]; then PAR_OPTS+=(--bar); fi

  # shellcheck disable=SC1083 # {1}..{5} are GNU Parallel placeholders, not Bash
  parallel "${PAR_OPTS[@]}" \
    range_worker {1} {2} {3} {4} {5} "$FILESIZE_MIN" "$FILESIZE_MAX" "$ROOT" \
    :::: "$tasks_file"

  echo "Done."
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
