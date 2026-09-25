// SPDX-License-Identifier: Apache-2.0
// Token parsing/ordering ported from the NeMo-derived Python implementation.
// Copyright NVIDIA CORPORATION and contributors; see NOTICE.
#include <kitten_text_processing/normalizer.hpp>
#include "graph.hpp"
#include "text.hpp"
#include <algorithm>
#include <numeric>
#include <optional>
#include <utility>

namespace kitten_text_processing {
namespace {
struct Value {
    enum Kind { Text, Object, Boolean, Null } kind = Object;
    std::string text;
    std::vector<std::pair<std::string,Value>> fields;
};
class Parser {
public:
    explicit Parser(std::string_view text) : text_(text) {}
    std::vector<Value> parse() {
        std::vector<Value> result;
        while (spaces()) {
            std::string key;
            while (position_ < text_.size() && key_char(text_[position_])) key.push_back(text_[position_++]);
            if (key.empty()) break;
            if (position_ == text_.size()) throw ParseError("Unexpected end of token key");
            spaces();
            Value value;
            if (key == "preserve_order") {
                expect(':'); spaces();
                for (char c : std::string("true")) expect(c);
                value.kind = Value::Boolean;
            } else if (at(':')) {
                expect(':'); spaces(); expect('"');
                value.kind = Value::Text;
                while (!(at('"') && position_+1 < text_.size() && text_[position_+1] == ' ')) {
                    if (position_ == text_.size()) throw ParseError("Unterminated token value");
                    value.text.push_back(text_[position_++]);
                }
                expect('"');
                if (value.text.empty()) value.kind = Value::Null;
            } else if (at('{')) {
                expect('{');
                for (auto& token : parse()) for (auto& field : token.fields) {
                    auto found = std::find_if(value.fields.begin(),value.fields.end(),
                        [&](const auto& prior) { return prior.first == field.first; });
                    if (found == value.fields.end()) value.fields.push_back(std::move(field));
                    else found->second = std::move(field.second);
                }
                expect('}');
            } else throw ParseError("Expected token value");
            Value token; token.fields.emplace_back(std::move(key),std::move(value));
            result.push_back(std::move(token));
        }
        return result;
    }
private:
    std::string_view text_;
    std::size_t position_ = 0;
    static bool key_char(char c) { return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || c == '_'; }
    bool at(char c) const { return position_ < text_.size() && text_[position_] == c; }
    bool spaces() { while (at(' ')) ++position_; return position_ < text_.size(); }
    void expect(char c) { if (!at(c)) throw ParseError("Unexpected token character"); ++position_; }
};
std::size_t estimate(const Value& value, std::size_t limit) {
    std::size_t count = 1;
    auto multiply = [&](std::size_t n) {
        if (count > limit / n) throw std::invalid_argument("Unsplittable token exceeds permutation limit");
        count *= n;
    };
    for (const auto& field : value.fields) if (field.second.kind == Value::Object)
        multiply(estimate(field.second,limit));
    for (std::size_t n=2; n<=value.fields.size(); ++n) multiply(n);
    return count;
}
std::vector<std::string> permutations(const Value& value) {
    std::vector<std::size_t> order(value.fields.size());
    std::iota(order.begin(),order.end(),0);
    bool preserve = std::any_of(value.fields.begin(),value.fields.end(),
        [](const auto& field) { return field.first == "preserve_order"; });
    std::vector<std::string> result;
    do {
        std::vector<std::string> partial{std::string()};
        for (auto i : order) {
            const auto& key = value.fields[i].first;
            const auto& inner = value.fields[i].second;
            if (inner.kind == Value::Text) {
                for (auto& s : partial) s += key + ": \"" + inner.text + "\" ";
            } else if (inner.kind == Value::Boolean) {
                for (auto& s : partial) s += key + ": true ";
            } else if (inner.kind == Value::Object) {
                auto recursive = permutations(inner);
                std::vector<std::string> product;
                for (const auto& left : partial) for (const auto& right : recursive)
                    product.push_back(left + " " + key + " { " + right + " } ");
                partial = std::move(product);
            } else throw std::invalid_argument("Empty token value");
        }
        for (auto& s : partial) result.push_back(std::move(s));
    } while (!preserve && std::next_permutation(order.begin(),order.end()));
    return result;
}
std::string escape(std::string_view text) {
    std::string result;
    for (char c : text) {
        if (c == '\\' || c == '[' || c == ']') result.push_back('\\');
        result.push_back(c);
    }
    return result;
}
NormalizerOptions validate(NormalizerOptions options) {
    options.lang = language_code(options.lang);
    if (options.input_case != "cased" && !(options.input_case == "lower_cased" &&
        (options.lang == "ko" || options.lang == "hy"))) throw std::invalid_argument("Unsupported input_case");
    if (!options.max_number_of_permutations_per_split) throw std::invalid_argument("Permutation limit must be positive");
    return options;
}
}
const std::vector<std::string>& supported_languages() {
    static const std::vector<std::string> languages = {"en","es","fr","de","pt","it","zh","ja","ko","hi","ar","ru","vi","hu","sv","hy","rw"};
    return languages;
}
std::string language_code(std::string_view locale) {
    auto end = locale.find_first_of("-_");
    std::string code(locale.substr(0,end));
    if (locale.empty()) code = "en";
    for (auto& c : code) if (c >= 'A' && c <= 'Z') c = static_cast<char>(c + ('a'-'A'));
    const auto& languages = supported_languages();
    if (std::find(languages.begin(),languages.end(),code) == languages.end())
        throw std::invalid_argument("Unsupported language: " + code);
    return code;
}
struct Normalizer::Impl {
    NormalizerOptions options;
    detail::Graph tagger, verbalizer;
    std::optional<detail::Graph> post;
    Impl(const std::filesystem::path& folder, NormalizerOptions opts)
        : options(validate(std::move(opts))), tagger(folder/options.lang/"tagger.fst"),
          verbalizer(folder/options.lang/"verbalizer.fst") {
        if (options.post_process && (options.lang == "en" || options.lang == "hi" || options.lang == "vi"))
            post.emplace(folder/options.lang/"post.fst",true);
    }
};
Normalizer::Normalizer(const std::filesystem::path& folder, NormalizerOptions options)
    : impl_(std::make_shared<Impl>(folder,std::move(options))) {}
const std::string& Normalizer::language() const noexcept { return impl_->options.lang; }
std::string Normalizer::normalize(std::string_view original, NormalizeOptions options) const {
    // Decode even when punctuation cleanup is disabled, validating UTF-8 once.
    auto text = detail::strip(options.punct_pre_process ? detail::pre_process(original) : std::string(original));
    if (text.empty()) return text;
    auto tagged = impl_->tagger.rewrite(text);
    if (tagged.empty()) throw ParseError("Empty tagger output");
    auto tokens = Parser(tagged).parse();
    auto limit = impl_->options.max_number_of_permutations_per_split;
    std::vector<std::pair<std::size_t,std::size_t>> groups;
    std::size_t start = 0, count = 1;
    for (std::size_t i=0; i<tokens.size(); ++i) {
        auto n = estimate(tokens[i],limit);
        if (count > limit / n) { groups.emplace_back(start,i); start = i; count = 1; }
        count *= n;
    }
    groups.emplace_back(start,tokens.size());
    std::string output;
    try {
        bool first = true;
        for (auto group : groups) {
            std::vector<std::vector<std::string>> choices;
            for (auto i=group.first; i<group.second; ++i) choices.push_back(permutations(tokens[i]));
            std::vector<std::size_t> indices(choices.size());
            bool success = false, more = true;
            while (more) {
                std::string candidate;
                for (std::size_t i=0; i<choices.size(); ++i) candidate += choices[i][indices[i]];
                try {
                    auto chunk = impl_->verbalizer.rewrite(candidate);
                    if (!first) output.push_back(' ');
                    output += chunk; first = false; success = true; break;
                } catch (const NoPathError&) {}
                more = false;
                for (std::size_t i=indices.size(); i>0; --i) {
                    if (++indices[i-1] < choices[i-1].size()) { more = true; break; }
                    indices[i-1] = 0;
                }
            }
            if (!success) return escape(text);
        }
    } catch (const std::invalid_argument&) { return escape(text); }
    output = detail::collapse_spaces(output);
    if (impl_->post && !detail::strip(output).empty()) output = impl_->post->rewrite(detail::strip(output));
    if (options.punct_post_process)
        output = detail::post_process_punct(original,detail::detokenize(output,language()));
    return output;
}
std::string Normalizer::normalize_text(std::string_view text) const {
    if (detail::strip(text).empty()) return std::string(text);
    return detail::strip(normalize(text,{false,true}));
}
std::vector<std::string> Normalizer::normalize_list(const std::vector<std::string>& texts, NormalizeOptions options) const {
    std::vector<std::string> result; result.reserve(texts.size());
    for (const auto& text : texts) result.push_back(normalize(text,options));
    return result;
}
} // namespace kitten_text_processing
