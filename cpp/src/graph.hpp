// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <cstdint>
#include <filesystem>
#include <string>
#include <vector>
namespace kitten_text_processing::detail {
class Graph {
public:
    explicit Graph(const std::filesystem::path& path, bool project_output = false);
    std::string rewrite(std::string text) const;
private:
    std::uint32_t start_ = 0;
    bool project_output_;
    std::vector<std::uint32_t> offsets_, labels_, targets_;
    std::vector<float> weights_, finals_;
};
}
