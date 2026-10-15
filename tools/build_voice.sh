#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
output=${1:-$root/build/voice/libkitten_voice_normalization.so}
mkdir -p "$(dirname "$output")"
${CXX:-g++} -std=c++17 -O3 -fPIC -shared -pthread \
  "$root/cpp/voice/voice_normalizer.cpp" \
  ${ICU_CFLAGS:-$(pkg-config --cflags icu-i18n)} \
  ${ICU_LIBS:-$(pkg-config --libs icu-i18n)} \
  -o "$output"
