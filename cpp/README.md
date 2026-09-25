# Standalone C++ normalizer

This is a C++17 implementation of the same written-to-spoken normalization used
by the pure Python package. It supports all 17 languages and uses the same NeMo
1.2.0 grammar arrays and frozen test cases. Python imports continue to use the
pure Python implementation. There are no Python bindings or automatic backend
selection in this version.

The C++ library has **no third-party runtime dependencies**: no Python, NeMo,
Pynini, OpenFst, or zlib. Its only runtime dependencies are the C++ standard
library and the prepared grammar files. Grammar loading, weighted decoding,
token ordering, Unicode handling, and punctuation cleanup all run in C++.

## Build

Use CMake 3.16+ and a C++17 compiler:

```sh
cmake -S . -B build/cpp -DCMAKE_BUILD_TYPE=Release
cmake --build build/cpp --parallel
build/cpp/kitten-normalize-cpp --data-dir build/cpp/data --lang en \
    --punct-post-process 'I paid $12.50 for 3 books.'
```

A standard-library-only Python 3.10+ helper decompresses and verifies the existing
shared grammar files during the default build. Python is **not** called by the
C++ library or executable. Prepared data occupies approximately 138 MiB across
all languages. A normalizer loads only its selected language; the Python package
continues to use the original compressed files.

To build on a machine without Python, prepare the data elsewhere:

```sh
python tools/export_cpp_data.py --output /path/to/prepared-data
# Copy the prepared directory along with the C++ source to the build machine.
cmake -S . -B build/cpp -DCMAKE_BUILD_TYPE=Release \
    -DKITTEN_DATA_DIR=/path/to/prepared-data -DBUILD_TESTING=OFF
cmake --build build/cpp --parallel
```

Static libraries are built by default. Add `-DBUILD_SHARED_LIBS=ON` for a shared
library. `-DKITTEN_BUILD_CLI=OFF` builds only the library (and tests if enabled).
Compile with IEEE-754 floating-point semantics; fast-math can change equal-cost
reading selection and is disabled on the library target.

## Use from another C++ application

Install the headers, library, CMake package configuration, licenses, and grammar
data together:

```sh
cmake --install build/cpp --prefix /path/to/install
```

In the consuming application's `CMakeLists.txt`:

```cmake
find_package(KittenTextProcessing CONFIG REQUIRED)
target_link_libraries(my_app PRIVATE KittenTextProcessing::normalizer)
```

Configure the application with `-DCMAKE_PREFIX_PATH=/path/to/install`.
`KittenTextProcessing_DATA_DIR` is the installed grammar directory, available to
the consuming CMake project. Pass a data directory explicitly to the C++ API;
there are no source-tree paths compiled into the library.

```cpp
#include <kitten_text_processing/normalizer.hpp>
#include <iostream>

int main() {
    kitten_text_processing::NormalizerOptions options;
    options.lang = "en";
    kitten_text_processing::Normalizer normalizer(
        "/path/to/install/share/kitten_text_processing", options);
    std::cout << normalizer.normalize_text("I have 2 cats.") << '\n';
}
```

A complete external consumer is in `cpp/examples`:

```sh
cmake -S cpp/examples -B build/example -DCMAKE_PREFIX_PATH=/path/to/install
cmake --build build/example
build/example/normalize_example /path/to/install/share/kitten_text_processing
```

## API behavior

The public API is in `cpp/include/kitten_text_processing/normalizer.hpp`.
All text is UTF-8 in `std::string`/`std::string_view`; malformed UTF-8 throws
`UnicodeError`. Embedded NUL bytes have the same semantics as the Python decoder.

- `NormalizerOptions`: `lang`, `input_case`, `post_process`, and
  `max_number_of_permutations_per_split`. Defaults match the Python class.
- `NormalizeOptions`: `punct_pre_process` and `punct_post_process`, both false
  by default, matching `Normalizer.normalize` in Python.
- `normalize(text, options)` returns the normalized string;
  `normalize_list(texts, options)` processes a vector of strings.
- `normalize_text(text)` enables punctuation cleanup and strips the result. Like
  the Python convenience API, it preserves empty and whitespace-only inputs.
- `language_code(locale)` handles locale tags such as `es_ES` and `en-US`.
- `supported_languages()` lists the same 17 languages as Python.
- `NoPathError` reports an input rejected by the grammar. Invalid configuration
  and unsplittable permutation groups throw `std::invalid_argument`; malformed
  classified tokens throw `ParseError`. File/format failures throw runtime errors.

Instances share immutable grammar data when copied. Concurrent normalization on
the same instance is supported; each call owns its lattice and parser state.
There is no global language cache. C++ callers control normalizer lifetime.
Separate instances load separate grammar arrays, so retain an instance for reuse.

Korean and Armenian accept `lower_cased` as an equivalent grammar alias. Russian
uses the same single minimum-weight reading as the Python package. Audio
rescoring, inverse normalization, custom grammars, and character spans are outside
both implementations' scope. Matching NeMo does not imply linguistic correctness
for every sentence; upstream rejections and ambiguous readings remain visible.

## Shared tests

```sh
ctest --test-dir build/cpp --output-on-failure
python -S tools/check_cpp.py --backend both
python -S -m unittest discover -s tests -v
```

The test runners read the **same existing files** in `tests/corpus`,
`tests/extended`, and `tests/regressions.json`: 25,475 normalization cases,
including 5,407 upstream fixture inputs. Expected outputs come from the pinned
NeMo oracle, not from the new C++ implementation. Errors are checked by category
and counted separately from successful outputs. The 18 upstream fixture
expectation disagreements are recorded in `tests/extended/manifest.json`.

`tests/decoder_cases.json` is shared by the Python decoder unit tests and the C++
decoder driver. It exercises negative weights, binary32 rounding, epsilon cycles,
output projection, Unicode byte labels, final weights, and equal-cost choices.
Native API checks cover configuration, errors, locales, lists, and concurrency.
The C++ loader also has malformed-file tests.

`tools/check_cpp.py` supports `--backend cpp|python|both`, `--languages en es`,
`--source corpus|extended|regressions|all`, and `--jobs 3`. Reports are written to
the ignored `.cache` directory. The corpus check uses Python only as a test
harness; it executes the C++ program as a separate process, without bindings.

The CLI's `--batch` protocol is intended for testing: each line contains seven
TAB-separated fields (`lang`, `input_case`, graph postprocessing 0/1, permutation
limit, punctuation preprocessing 0/1, punctuation postprocessing 0/1, hex-encoded
UTF-8 input). Responses are `OK<TAB>hex-output` or
`ERR<TAB>error-category<TAB>hex-message`. This preserves embedded NUL, newlines,
and whitespace. Human-facing CLI use accepts text as an argument; `--help` lists
its options. `KITTEN_TEXT_PROCESSING_DATA_DIR` can supply its data directory.
