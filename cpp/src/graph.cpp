// SPDX-License-Identifier: Apache-2.0
// Python decoder port. Traversal and epsilon-removal ordering follow OpenFst
// (Copyright Google, Inc., Apache-2.0); see NOTICE.
#include "graph.hpp"
#include <kitten_text_processing/normalizer.hpp>
#include <algorithm>
#include <cmath>
#include <cstring>
#include <deque>
#include <fstream>
#include <limits>
#include <unordered_map>
#include <unordered_set>

namespace kitten_text_processing::detail {
namespace {
constexpr float inf = std::numeric_limits<float>::infinity();
constexpr std::size_t absent = std::numeric_limits<std::size_t>::max();
// Force rounding after every addition even on machines with excess precision.
float add(float a, float b) { volatile float result = a + b; return result; }
struct Edge { std::size_t target; float weight; unsigned char output; };
struct Node {
    std::size_t position;
    std::uint32_t state;
    std::vector<Edge> edges;
    unsigned char color = 0;
    bool live = false;
    float final = inf;
};
using Lattice = std::vector<Node>;
std::vector<std::size_t> finish_order(const Lattice& nodes) {
    std::vector<unsigned char> seen(nodes.size());
    std::vector<std::pair<std::size_t,std::size_t>> stack{{0,0}};
    std::vector<std::size_t> order;
    seen[0] = 1;
    while (!stack.empty()) {
        auto id = stack.back().first;
        auto& i = stack.back().second;
        if (i == nodes[id].edges.size()) { order.push_back(id); stack.pop_back(); }
        else {
            auto target = nodes[id].edges[i++].target;
            if (!seen[target]) { seen[target] = 1; stack.emplace_back(target,0); }
        }
    }
    return order;
}
void project(Lattice& nodes, std::vector<std::size_t>& order) {
    std::vector<bool> incoming(nodes.size());
    incoming[0] = true;
    for (const auto& node : nodes) if (node.live)
        for (auto edge : node.edges) if (edge.output && nodes[edge.target].live)
            incoming[edge.target] = true;
    for (auto source : order) {
        if (!nodes[source].live || !incoming[source]) continue;
        std::unordered_map<std::size_t,float> distances{{source,0}};
        std::deque<std::size_t> pending{source};
        std::unordered_set<std::size_t> queued{source};
        while (!pending.empty()) {
            auto id = pending.front(); pending.pop_front(); queued.erase(id);
            for (auto edge : nodes[id].edges) {
                if (edge.output || !nodes[edge.target].live) continue;
                float candidate = add(distances.at(id), edge.weight);
                auto old = distances.find(edge.target);
                if (old == distances.end() || candidate < old->second) {
                    distances[edge.target] = candidate;
                    if (queued.insert(edge.target).second) pending.push_back(edge.target);
                }
            }
        }
        std::vector<Edge> expanded;
        std::unordered_map<std::uint64_t,std::size_t> index;
        float final = inf;
        std::vector<std::size_t> stack{source};
        std::unordered_set<std::size_t> seen;
        while (!stack.empty()) {
            auto id = stack.back(); stack.pop_back();
            if (!seen.insert(id).second) continue;
            float distance = distances.at(id);
            final = std::min(final, add(distance, nodes[id].final));
            for (auto edge : nodes[id].edges) {
                if (!nodes[edge.target].live) continue;
                if (!edge.output) { if (!seen.count(edge.target)) stack.push_back(edge.target); }
                else {
                    std::uint64_t key = (std::uint64_t(edge.target) << 8) | edge.output;
                    float weight = add(distance, edge.weight);
                    auto found = index.find(key);
                    if (found == index.end()) {
                        index.emplace(key,expanded.size());
                        expanded.push_back({edge.target,weight,edge.output});
                    } else expanded[found->second].weight = std::min(expanded[found->second].weight,weight);
                }
            }
        }
        std::reverse(expanded.begin(),expanded.end());
        nodes[source].edges = std::move(expanded);
        nodes[source].final = final;
    }
    order = finish_order(nodes);
    for (auto& node : nodes) node.live = false;
    for (auto id : order) nodes[id].live = true;
}
}

Graph::Graph(const std::filesystem::path& path, bool project_output) : project_output_(project_output) {
    static_assert(sizeof(float) == 4 && std::numeric_limits<float>::is_iec559,
                  "IEEE-754 binary32 floats are required");
    std::ifstream file(path, std::ios::binary | std::ios::ate);
    if (!file) throw std::runtime_error("Cannot open grammar: " + path.string());
    auto size = file.tellg();
    if (size < 20) throw std::runtime_error("Truncated grammar: " + path.string());
    file.seekg(0);
    std::vector<unsigned char> data(static_cast<std::size_t>(size));
    if (!file.read(reinterpret_cast<char*>(data.data()),size)) throw std::runtime_error("Cannot read grammar");
    if (std::memcmp(data.data(),"KITTEN1\0",8)) throw std::runtime_error("Invalid grammar header");
    std::size_t cursor = 8;
    auto read = [&]() {
        auto p = data.data() + cursor; cursor += 4;
        return std::uint32_t(p[0]) | (std::uint32_t(p[1]) << 8) |
               (std::uint32_t(p[2]) << 16) | (std::uint32_t(p[3]) << 24);
    };
    start_ = read(); auto states = read(); auto arcs = read();
    if (!states || start_ >= states || 24ULL + 8ULL*states + 12ULL*arcs != data.size())
        throw std::runtime_error("Invalid grammar dimensions");
    offsets_.resize(std::size_t(states)+1); finals_.resize(states);
    labels_.resize(arcs); targets_.resize(arcs); weights_.resize(arcs);
    for (auto& v : offsets_) v = read();
    auto read_float = [&]() { auto bits = read(); float v; std::memcpy(&v,&bits,4); return v; };
    for (auto& v : finals_) v = read_float();
    for (auto& v : labels_) v = read();
    for (auto& v : targets_) v = read();
    for (auto& v : weights_) v = read_float();
    if (offsets_.front() || offsets_.back() != arcs || !std::is_sorted(offsets_.begin(),offsets_.end()))
        throw std::runtime_error("Invalid grammar offsets");
    for (std::size_t i=0; i<arcs; ++i)
        if (targets_[i] >= states || labels_[i] > 65535 || !std::isfinite(weights_[i]))
            throw std::runtime_error("Invalid grammar arc");
    for (auto weight : finals_) if (std::isnan(weight) || weight == -inf)
        throw std::runtime_error("Invalid final weight");
}

std::string Graph::rewrite(std::string text) const {
    text.erase(std::remove(text.begin(),text.end(),'\0'),text.end());
    if (text.size() > std::numeric_limits<std::uint32_t>::max()) throw std::length_error("Input too long");
    Lattice nodes;
    std::unordered_map<std::uint64_t,std::size_t> index;
    auto intern = [&](std::size_t position, std::uint32_t state) {
        std::uint64_t key = (std::uint64_t(position) << 32) | state;
        auto found = index.find(key);
        if (found != index.end()) return found->second;
        auto id = nodes.size(); index.emplace(key,id);
        nodes.push_back({position,state,{},0,false,position == text.size() ? finals_[state] : inf});
        return id;
    };
    intern(0,start_);
    auto discover = [&](std::size_t id) {
        auto position = nodes[id].position; auto state = nodes[id].state;
        std::vector<Edge> edges;
        // Epsilon arcs precede consuming arcs, preserving order within each group.
        for (int pass=0; pass<2; ++pass) {
            if (pass && position == text.size()) break;
            unsigned label = pass ? static_cast<unsigned char>(text[position]) : 0;
            for (auto i=offsets_[state]; i<offsets_[state+1]; ++i) if ((labels_[i] & 255) == label) {
                auto target = intern(position + (pass ? 1 : 0), targets_[i]);
                edges.push_back({target,weights_[i],static_cast<unsigned char>(labels_[i] >> 8)});
            }
        }
        nodes[id].edges = std::move(edges); nodes[id].color = 1;
    };
    discover(0);
    std::vector<std::pair<std::size_t,std::size_t>> stack{{0,0}};
    std::vector<std::size_t> order;
    bool cyclic = false;
    while (!stack.empty()) {
        auto id = stack.back().first;
        auto& i = stack.back().second;
        if (i == nodes[id].edges.size()) {
            auto& node = nodes[id];
            node.live = std::isfinite(node.final) || std::any_of(node.edges.begin(),node.edges.end(),
                [&](const Edge& edge) { return nodes[edge.target].live; });
            node.color = 2; order.push_back(id); stack.pop_back();
        } else {
            auto target = nodes[id].edges[i++].target;
            if (nodes[target].color == 1) cyclic = true;
            if (!nodes[target].color) { discover(target); stack.emplace_back(target,0); }
        }
    }
    if (cyclic) {
        std::vector<std::vector<std::size_t>> reverse(nodes.size());
        std::vector<std::size_t> pending;
        for (std::size_t i=0; i<nodes.size(); ++i) {
            if (nodes[i].live) pending.push_back(i);
            for (auto edge : nodes[i].edges) reverse[edge.target].push_back(i);
        }
        while (!pending.empty()) {
            auto id = pending.back(); pending.pop_back();
            for (auto parent : reverse[id]) if (!nodes[parent].live) {
                nodes[parent].live = true; pending.push_back(parent);
            }
        }
    }
    if (!nodes[0].live) throw NoPathError("No accepting path");
    if (project_output_) project(nodes,order);
    std::vector<float> costs(nodes.size(),inf);
    std::vector<std::pair<std::size_t,unsigned char>> parents(nodes.size(),{absent,0});
    std::vector<bool> queued(nodes.size());
    std::deque<std::size_t> pending;
    for (auto it=order.rbegin(); it!=order.rend(); ++it) if (nodes[*it].live) {
        pending.push_back(*it); queued[*it] = true;
    }
    costs[0] = 0; float best = inf; std::size_t final = absent;
    while (!pending.empty()) {
        auto id = pending.front(); pending.pop_front(); queued[id] = false;
        float cost = costs[id];
        if (!std::isfinite(cost)) continue;
        float candidate = add(cost,nodes[id].final);
        if (candidate < best) { best = candidate; final = id; }
        for (auto edge : nodes[id].edges) if (nodes[edge.target].live) {
            candidate = add(cost,edge.weight);
            if (candidate < costs[edge.target]) {
                costs[edge.target] = candidate; parents[edge.target] = {id,edge.output};
                if (!queued[edge.target]) { pending.push_back(edge.target); queued[edge.target] = true; }
            }
        }
    }
    if (final == absent) throw NoPathError("No accepting path");
    std::string result;
    for (auto id=final; id; id=parents[id].first) {
        if (parents[id].first == absent) throw std::logic_error("Broken decoder path");
        if (parents[id].second) result.push_back(static_cast<char>(parents[id].second));
    }
    std::reverse(result.begin(),result.end());
    return result;
}
} // namespace kitten_text_processing::detail
