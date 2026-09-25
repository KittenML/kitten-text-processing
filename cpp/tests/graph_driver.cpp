// SPDX-License-Identifier: Apache-2.0
#include "graph.hpp"
#include <kitten_text_processing/normalizer.hpp>
#include <iostream>
int main(int argc, char** argv) {
    try {
        if (argc!=4) throw std::invalid_argument("Expected graph, projection flag, input");
        kitten_text_processing::detail::Graph graph(argv[1],std::string(argv[2])=="1");
        std::cout << graph.rewrite(argv[3]);
        return 0;
    } catch (const kitten_text_processing::NoPathError&) { return 2; }
      catch (const std::exception& error) { std::cerr << error.what(); return 1; }
}
