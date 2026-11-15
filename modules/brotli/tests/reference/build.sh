#!/bin/sh
# Builds the reference tool from a checkout of google/brotli at the pinned commit
# (028fb5a23661f123017c060daa546b55cf4bde29, v1.2.0) with patched/, upstream 0ed4268's decoder.
#   tests/reference/build.sh <brotli checkout> <output executable>
set -eu
here=$(cd "$(dirname "$0")" && pwd)
src=$1
out=$2
${CC:-cc} -O2 -w -I "$here/patched/include" -I "$src/c/include" -I "$src/c/dec" \
  "$here/ref_tool.c" "$src"/c/common/*.c "$src"/c/enc/*.c \
  "$src/c/dec/bit_reader.c" "$src/c/dec/huffman.c" "$src/c/dec/prefix.c" "$src/c/dec/state.c" "$src/c/dec/static_init.c" \
  "$here/patched/dec/decode.c" -lm -o "$out"
