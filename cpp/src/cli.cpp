// SPDX-License-Identifier: Apache-2.0
#include <kitten_text_processing/normalizer.hpp>
#include <cstdlib>
#include <iostream>
#include <memory>
#include <sstream>
#include <tuple>

namespace ktp = kitten_text_processing;
namespace {
std::string unhex(const std::string& value) {
    if (value.size()%2) throw std::invalid_argument("Odd hex length");
    auto digit = [](char c) -> unsigned {
        if (c >= '0' && c <= '9') return c-'0';
        if (c >= 'a' && c <= 'f') return c-'a'+10;
        if (c >= 'A' && c <= 'F') return c-'A'+10;
        throw std::invalid_argument("Invalid hex digit");
    };
    std::string result;
    for (std::size_t i=0; i<value.size(); i+=2) result.push_back(static_cast<char>((digit(value[i])<<4)|digit(value[i+1])));
    return result;
}
std::string hex(std::string_view value) {
    constexpr char digits[] = "0123456789abcdef";
    std::string result;
    for (unsigned char c : value) { result.push_back(digits[c>>4]); result.push_back(digits[c&15]); }
    return result;
}
void batch(const std::filesystem::path& data) {
    std::unique_ptr<ktp::Normalizer> model;
    std::tuple<std::string,std::string,bool,std::size_t> previous;
    std::string line;
    while (std::getline(std::cin,line)) {
        try {
            std::vector<std::string> fields;
            std::size_t start=0, end;
            while ((end=line.find('\t',start)) != std::string::npos) {
                fields.push_back(line.substr(start,end-start)); start=end+1;
            }
            fields.push_back(line.substr(start));
            if (fields.size()!=7) throw std::invalid_argument("Expected seven tab-separated fields");
            ktp::NormalizerOptions options;
            options.lang=fields[0]; options.input_case=fields[1]; options.post_process=fields[2]=="1";
            options.max_number_of_permutations_per_split=std::stoull(fields[3]);
            auto key=std::make_tuple(options.lang,options.input_case,options.post_process,options.max_number_of_permutations_per_split);
            if (!model || key!=previous) { model=std::make_unique<ktp::Normalizer>(data,options); previous=key; }
            auto output=model->normalize(unhex(fields[6]),{fields[4]=="1",fields[5]=="1"});
            std::cout << "OK\t" << hex(output) << '\n';
        } catch (const ktp::NoPathError& e) { std::cout << "ERR\tNoPathError\t" << hex(e.what()) << '\n'; }
          catch (const ktp::UnicodeError& e) { std::cout << "ERR\tUnicodeError\t" << hex(e.what()) << '\n'; }
          catch (const ktp::ParseError& e) { std::cout << "ERR\tParseError\t" << hex(e.what()) << '\n'; }
          catch (const std::invalid_argument& e) { std::cout << "ERR\tValueError\t" << hex(e.what()) << '\n'; }
          catch (const std::exception& e) { std::cout << "ERR\tRuntimeError\t" << hex(e.what()) << '\n'; }
        std::cout.flush();
    }
}
}
int main(int argc, char** argv) {
    try {
        std::filesystem::path data;
        if (const char* env=std::getenv("KITTEN_TEXT_PROCESSING_DATA_DIR")) data=env;
        ktp::NormalizerOptions constructor;
        ktp::NormalizeOptions options;
        bool use_batch=false, literal=false;
        std::string text;
        for (int i=1; i<argc; ++i) {
            std::string arg=argv[i];
            auto value=[&]() -> std::string { if (++i==argc) throw std::invalid_argument("Missing option value"); return argv[i]; };
            if (!literal && arg=="--data-dir") data=value();
            else if (!literal && arg=="--lang") constructor.lang=value();
            else if (!literal && arg=="--input-case") constructor.input_case=value();
            else if (!literal && arg=="--no-post-process") constructor.post_process=false;
            else if (!literal && arg=="--punct-pre-process") options.punct_pre_process=true;
            else if (!literal && arg=="--punct-post-process") options.punct_post_process=true;
            else if (!literal && arg=="--batch") use_batch=true;
            else if (!literal && arg=="--") literal=true;
            else if (!literal && (arg=="--help" || arg=="-h")) {
                std::cout << "Usage: kitten-normalize-cpp --data-dir PATH [--lang en] [--input-case cased]\n"
                             "       [--no-post-process] [--punct-pre-process] [--punct-post-process] TEXT\n"
                             "       --batch uses the documented tab-separated test protocol.\n";
                return 0;
            } else if (!literal && arg.rfind("--",0)==0) throw std::invalid_argument("Unknown option: "+arg);
            else { if (!text.empty()) text+=' '; text+=arg; }
        }
        if (data.empty()) throw std::invalid_argument("Pass --data-dir or set KITTEN_TEXT_PROCESSING_DATA_DIR");
        if (use_batch) batch(data);
        else std::cout << ktp::Normalizer(data,constructor).normalize(text,options) << '\n';
        return 0;
    } catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
}
