// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <string>
#include <string_view>
namespace kitten_text_processing::detail {
std::u32string decode(std::string_view text);
std::string encode(std::u32string_view text);
bool whitespace(char32_t c);
std::string strip(std::string_view text);
std::string collapse_spaces(std::string_view text);
std::string pre_process(std::string_view text);
std::string detokenize(std::string_view text, const std::string& lang);
std::string post_process_punct(std::string_view input, std::string_view normalized);
}
