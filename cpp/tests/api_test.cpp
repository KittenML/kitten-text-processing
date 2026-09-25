// SPDX-License-Identifier: Apache-2.0
#include <kitten_text_processing/normalizer.hpp>
#include <future>
#include <iostream>
namespace ktp = kitten_text_processing;
void require(bool condition) { if (!condition) throw std::runtime_error("C++ API test failed"); }
template<class Error, class F> void throws(F function) {
    try { function(); } catch (const Error&) { return; }
    throw std::runtime_error("Expected exception was not raised");
}
int main(int argc, char** argv) {
    try {
        require(argc==2);
        ktp::Normalizer en(argv[1]);
        require(en.normalize("2")=="two");
        require(en.normalize_text("I have 2 cats.")=="I have two cats.");
        require(en.normalize_text("  ")=="  ");
        require(en.normalize("  ").empty());
        require(en.normalize_list({"2","3"})==std::vector<std::string>({"two","three"}));
        require(ktp::language_code("en_US")=="en");
        throws<std::invalid_argument>([] { ktp::language_code("xx"); });
        throws<ktp::UnicodeError>([&] { en.normalize(std::string("\xed\xa0\x80")); });
        ktp::NormalizerOptions options; options.max_number_of_permutations_per_split=1;
        ktp::Normalizer limited(argv[1],options);
        throws<std::invalid_argument>([&] { limited.normalize("$12.50"); });
        options={}; options.input_case="lower_cased";
        throws<std::invalid_argument>([&] { ktp::Normalizer invalid(argv[1],options); });
        for (const auto& lang : {"ko","hy"}) {
            options.lang=lang; ktp::Normalizer lower(argv[1],options);
            options.input_case="cased"; ktp::Normalizer cased(argv[1],options);
            require(lower.normalize("12")==cased.normalize("12"));
            options.input_case="lower_cased";
        }
        std::vector<std::future<std::string>> tasks;
        for (int i=0; i<8; ++i) tasks.push_back(std::async(std::launch::async,[&] { return en.normalize_text("I have 2 cats."); }));
        for (auto& task : tasks) require(task.get()=="I have two cats.");
        std::cout << "C++ API, UTF-8, error, locale, options and concurrency checks passed\n";
        return 0;
    } catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
}
