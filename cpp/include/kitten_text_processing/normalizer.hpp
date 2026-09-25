// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <filesystem>
#include <memory>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

namespace kitten_text_processing {
class NoPathError : public std::runtime_error { using std::runtime_error::runtime_error; };
class UnicodeError : public std::invalid_argument { using std::invalid_argument::invalid_argument; };
class ParseError : public std::runtime_error { using std::runtime_error::runtime_error; };
struct NormalizerOptions {
    std::string lang = "en";
    std::string input_case = "cased";
    bool post_process = true;
    std::size_t max_number_of_permutations_per_split = 729;
};
struct NormalizeOptions {
    bool punct_pre_process = false;
    bool punct_post_process = false;
};
const std::vector<std::string>& supported_languages();
std::string language_code(std::string_view locale);
// data_dir contains en/tagger.fst, en/verbalizer.fst, etc. All strings are UTF-8.
// Instances are immutable after construction and may be shared across threads.
class Normalizer {
public:
    explicit Normalizer(const std::filesystem::path& data_dir, NormalizerOptions options = {});
    std::string normalize(std::string_view text, NormalizeOptions options = {}) const;
    std::vector<std::string> normalize_list(const std::vector<std::string>& texts,
                                          NormalizeOptions options = {}) const;
    // Convenience form: punctuation cleanup enabled, surrounding whitespace stripped.
    std::string normalize_text(std::string_view text) const;
    const std::string& language() const noexcept;
private:
    struct Impl;
    std::shared_ptr<const Impl> impl_;
};
} // namespace kitten_text_processing
