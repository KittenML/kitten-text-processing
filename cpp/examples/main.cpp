// SPDX-License-Identifier: Apache-2.0
#include <kitten_text_processing/normalizer.hpp>
#include <iostream>
int main(int argc, char** argv) {
    if (argc != 2) {
        std::cerr << "Usage: normalize_example /path/to/share/kitten_text_processing\n";
        return 1;
    }
    try {
        kitten_text_processing::NormalizerOptions options;
        options.lang = "en";
        kitten_text_processing::Normalizer normalizer(argv[1],options);
        std::cout << normalizer.normalize_text("I paid $12.50 for 3 books.") << '\n';
    } catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
}
