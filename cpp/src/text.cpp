// SPDX-License-Identifier: Apache-2.0
// Ports of the Python punctuation helpers adapted from NeMo (Copyright NVIDIA
// CORPORATION, Apache-2.0), and Sacremoses-compatible detokenization. See NOTICE.
#include "text.hpp"
#include "unicode_data.hpp"
#include <kitten_text_processing/normalizer.hpp>
#include <algorithm>
#include <iterator>
#include <map>
#include <vector>

namespace kitten_text_processing::detail {
std::u32string decode(std::string_view text) {
    std::u32string result;
    for (std::size_t i=0; i<text.size();) {
        unsigned char first = static_cast<unsigned char>(text[i++]);
        char32_t c = first; unsigned count = 0; char32_t minimum = 0;
        if (first >= 0xc2 && first <= 0xdf) { c = first & 31; count = 1; minimum = 0x80; }
        else if (first >= 0xe0 && first <= 0xef) { c = first & 15; count = 2; minimum = 0x800; }
        else if (first >= 0xf0 && first <= 0xf4) { c = first & 7; count = 3; minimum = 0x10000; }
        else if (first >= 0x80) throw UnicodeError("Invalid UTF-8 leading byte");
        for (unsigned k=0; k<count; ++k) {
            if (i == text.size()) throw UnicodeError("Truncated UTF-8 sequence");
            auto next = static_cast<unsigned char>(text[i++]);
            if ((next & 0xc0) != 0x80) throw UnicodeError("Invalid UTF-8 continuation byte");
            c = (c << 6) | (next & 63);
        }
        if (c < minimum || c > 0x10ffff || (c >= 0xd800 && c <= 0xdfff))
            throw UnicodeError("Invalid Unicode scalar value");
        result.push_back(c);
    }
    return result;
}
std::string encode(std::u32string_view text) {
    std::string result;
    for (char32_t c : text) {
        if (c < 0x80) result.push_back(static_cast<char>(c));
        else if (c < 0x800) {
            result.push_back(static_cast<char>(0xc0 | (c >> 6)));
            result.push_back(static_cast<char>(0x80 | (c & 63)));
        } else if (c < 0x10000 && !(c >= 0xd800 && c <= 0xdfff)) {
            result.push_back(static_cast<char>(0xe0 | (c >> 12)));
            result.push_back(static_cast<char>(0x80 | ((c >> 6) & 63)));
            result.push_back(static_cast<char>(0x80 | (c & 63)));
        } else if (c >= 0x10000 && c <= 0x10ffff) {
            result.push_back(static_cast<char>(0xf0 | (c >> 18)));
            result.push_back(static_cast<char>(0x80 | ((c >> 12) & 63)));
            result.push_back(static_cast<char>(0x80 | ((c >> 6) & 63)));
            result.push_back(static_cast<char>(0x80 | (c & 63)));
        } else throw UnicodeError("Invalid Unicode scalar value");
    }
    return result;
}
bool whitespace(char32_t c) {
    return (c >= 9 && c <= 13) || (c >= 28 && c <= 32) || c == 0x85 || c == 0xa0 ||
        c == 0x1680 || (c >= 0x2000 && c <= 0x200a) || c == 0x2028 || c == 0x2029 ||
        c == 0x202f || c == 0x205f || c == 0x3000;
}
std::string strip(std::string_view text) {
    auto unicode = decode(text);
    std::size_t first = 0, last = unicode.size();
    while (first < last && whitespace(unicode[first])) ++first;
    while (last > first && whitespace(unicode[last-1])) --last;
    return encode(std::u32string_view(unicode).substr(first,last-first));
}
std::string collapse_spaces(std::string_view text) {
    std::string result;
    for (char c : text) if (c != ' ' || result.empty() || result.back() != ' ') result.push_back(c);
    return result;
}
std::string pre_process(std::string_view text) {
    std::string result;
    for (char c : text) {
        if (c == '[' || c == ']') result.push_back(' ');
        result.push_back(c);
        if (c == '[' || c == ']') result.push_back(' ');
    }
    return collapse_spaces(result);
}
namespace {
bool contains(std::u32string_view chars, char32_t c) { return chars.find(c) != std::u32string_view::npos; }
bool alpha(char32_t c) {
    auto it = std::upper_bound(std::begin(alpha_ranges),std::end(alpha_ranges),c,
        [](char32_t value, const auto& range) { return value < range.first; });
    return it != std::begin(alpha_ranges) && c <= std::prev(it)->second;
}
bool cjk(char32_t c) {
    constexpr std::pair<char32_t,char32_t> ranges[] = {
        {4352,4607},{11904,42191},{43072,43135},{44032,55215},{63744,64255},
        {65072,65103},{65381,65500},{94208,101119},{110592,110895},
        {110960,111359},{131072,196607}};
    for (auto range : ranges) if (range.first <= c && c <= range.second) return true;
    return false;
}
void replace_all(std::u32string& text, std::u32string_view from, std::u32string_view to) {
    std::size_t pos = 0;
    while ((pos = text.find(from,pos)) != std::u32string::npos) {
        text.replace(pos,from.size(),to); pos += to.size();
    }
}
}
std::string detokenize(std::string_view text, const std::string& lang) {
    auto unicode = U" " + decode(text) + U" ";
    replace_all(unicode,U" @-@ ",U"-");
    std::vector<std::u32string> tokens;
    std::size_t i = 0;
    while (i < unicode.size()) {
        while (i < unicode.size() && whitespace(unicode[i])) ++i;
        auto start = i;
        while (i < unicode.size() && !whitespace(unicode[i])) ++i;
        if (i > start) tokens.push_back(unicode.substr(start,i-start));
    }
    std::map<std::u32string,std::size_t> quotes;
    std::u32string space = U" ", result;
    for (i=0; i<tokens.size(); ++i) {
        const auto& token = tokens[i];
        auto all = [&](std::u32string_view set) { return std::all_of(token.begin(),token.end(),
            [&](char32_t c) { return contains(set,c); }); };
        if (cjk(token.front()) && lang != "ko") {
            result += (i && cjk(tokens[i-1].back()) ? U"" : space) + token; space = U" ";
        } else if (std::all_of(token.begin(),token.end(),[](char32_t c) {
            return contains(U"([{¿¡",c) || std::find(std::begin(currency_symbols),std::end(currency_symbols),c) != std::end(currency_symbols);
        })) { result += space + token; space.clear(); }
        else if (all(U",.?!:;\\%}])")) {
            result += (lang == "fr" && token.size() == 1 && contains(U"?!:;\\%",token.front()) ? U" " : U"") + token;
            space = U" ";
        } else if (lang == "en" && i && token.size() > 1 && token.front() == U'\'' && alpha(token[1])) {
            result += token; space = U" ";
        } else if ((lang == "fr" || lang == "it") && i+1 < tokens.size() && token.size() > 1 &&
                   token.back() == U'\'' && alpha(token[token.size()-2]) && alpha(tokens[i+1].front())) {
            result += space + token; space.clear();
        } else if (all(U"'\"„“`")) {
            auto key = all(U"„“”") ? std::u32string(U"\"") : token;
            auto count = quotes[key];
            if (count % 2 || (lang == "en" && token == U"'" && i && tokens[i-1].back() == U's')) {
                result += token; space = U" "; if (count % 2) quotes[key] = count + 1;
            } else { result += space + token; space.clear(); quotes[key] = count + 1; }
        } else { result += space + token; space = U" "; }
    }
    return strip(collapse_spaces(encode(result)));
}
std::string post_process_punct(std::string_view input, std::string_view normalized) {
    auto original = decode(input), output = decode(normalized);
    if (original.find(U"``") != std::u32string::npos && output.find(U"``") == std::u32string::npos)
        replace_all(original,U"``",U"\"");
    // Keep character positions stable while entries are erased or gain spaces,
    // exactly as the Python list-based punctuation matching algorithm does.
    std::vector<std::u32string> before, after;
    for (auto c : original) before.emplace_back(1,c);
    for (auto c : output) after.emplace_back(1,c);
    for (char32_t punct : std::u32string_view(U"!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~")) {
        std::u32string mark(1,punct);
        auto n = std::count(before.begin(),before.end(),mark);
        if (!n) continue;
        bool equal = n == std::count(after.begin(),after.end(),mark);
        std::size_t in = 0, out = 0;
        while (in < before.size()) {
            auto found_in = std::find(before.begin()+in,before.end(),mark);
            if (found_in == before.end()) break;
            auto found_out = std::find(after.begin()+out,after.end(),mark);
            if (found_out == after.end()) break;
            in = static_cast<std::size_t>(found_in-before.begin());
            out = static_cast<std::size_t>(found_out-after.begin());
            bool valid = (out && in && after[out-1] == before[in-1]) ||
                (out+1 < after.size() && in+1 < before.size() && after[out+1] == before[in+1]);
            if (!equal && !valid) { ++in; continue; }
            if (in && out) {
                if (after[out-1] == U" " && before[in-1] != U" ") after[out-1].clear();
                else if (after[out-1] != U" " && before[in-1] == U" ") after[out-1] += U" ";
            }
            if (in+1 < before.size() && out+1 < after.size()) {
                if (after[out+1] == U" " && before[in+1] != U" ") after[out+1].clear();
                else if (after[out+1] != U" " && before[in+1] == U" ") after[out] += U" ";
            }
            ++in; ++out;
        }
    }
    std::u32string result;
    for (const auto& s : after) result += s;
    return collapse_spaces(encode(result));
}
} // namespace kitten_text_processing::detail
