cmake_minimum_required(VERSION 3.16)
project(KittenTextProcessing VERSION 0.1.0 LANGUAGES CXX)
include(GNUInstallDirs)
include(CMakePackageConfigHelpers)
include(CTest)

set(KITTEN_DATA_DIR "" CACHE PATH "Prepared uncompressed grammar directory; avoids Python at build time")
option(KITTEN_BUILD_CLI "Build the standalone C++ command-line program" ON)
if(NOT KITTEN_DATA_DIR)
    find_package(Python3 3.10 REQUIRED COMPONENTS Interpreter)
    set(KITTEN_DATA_DIR "${CMAKE_CURRENT_BINARY_DIR}/data")
    file(GLOB_RECURSE grammar_sources CONFIGURE_DEPENDS
        "${CMAKE_CURRENT_SOURCE_DIR}/kitten_text_processing/data/*.gz"
        "${CMAKE_CURRENT_SOURCE_DIR}/kitten_text_processing/data/*.json")
    add_custom_command(OUTPUT "${KITTEN_DATA_DIR}/.ready"
        COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tools/export_cpp_data.py"
                --source "${CMAKE_CURRENT_SOURCE_DIR}/kitten_text_processing/data" --output "${KITTEN_DATA_DIR}"
        COMMAND "${CMAKE_COMMAND}" -E touch "${KITTEN_DATA_DIR}/.ready"
        DEPENDS ${grammar_sources} "${CMAKE_CURRENT_SOURCE_DIR}/tools/export_cpp_data.py"
        COMMENT "Preparing shared grammar data (build time only)" VERBATIM)
    add_custom_target(kitten_grammar_data ALL DEPENDS "${KITTEN_DATA_DIR}/.ready")
elseif(NOT EXISTS "${KITTEN_DATA_DIR}/en/tagger.fst")
    message(FATAL_ERROR "KITTEN_DATA_DIR must contain prepared language/*.fst files")
endif()

add_library(kitten_text_processing_cpp cpp/src/graph.cpp cpp/src/text.cpp cpp/src/normalizer.cpp)
add_library(KittenTextProcessing::normalizer ALIAS kitten_text_processing_cpp)
if(TARGET kitten_grammar_data)
    add_dependencies(kitten_text_processing_cpp kitten_grammar_data)
endif()
set_target_properties(kitten_text_processing_cpp PROPERTIES
    OUTPUT_NAME kitten_text_processing EXPORT_NAME normalizer
    VERSION ${PROJECT_VERSION} SOVERSION 0 WINDOWS_EXPORT_ALL_SYMBOLS ON)
target_compile_features(kitten_text_processing_cpp PUBLIC cxx_std_17)
target_include_directories(kitten_text_processing_cpp PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/cpp/include>
    $<INSTALL_INTERFACE:${CMAKE_INSTALL_INCLUDEDIR}>)
if(MSVC)
    target_compile_options(kitten_text_processing_cpp PRIVATE /W4 /fp:strict /utf-8)
else()
    target_compile_options(kitten_text_processing_cpp PRIVATE -Wall -Wextra -Wpedantic -fno-fast-math -ffp-contract=off)
endif()
if(KITTEN_BUILD_CLI)
    add_executable(kitten-normalize-cpp cpp/src/cli.cpp)
    target_link_libraries(kitten-normalize-cpp PRIVATE KittenTextProcessing::normalizer)
    install(TARGETS kitten-normalize-cpp RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR})
endif()

install(TARGETS kitten_text_processing_cpp EXPORT KittenTextProcessingTargets
    ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR} LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}
    RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR})
install(DIRECTORY cpp/include/ DESTINATION ${CMAKE_INSTALL_INCLUDEDIR})
set(KITTEN_INSTALL_DATA_DIR "${CMAKE_INSTALL_DATADIR}/kitten_text_processing")
install(DIRECTORY "${KITTEN_DATA_DIR}/" DESTINATION "${KITTEN_INSTALL_DATA_DIR}"
    FILES_MATCHING PATTERN "*.fst" PATTERN "metadata.json")
install(FILES LICENSE LICENSE-SACREMOSES NOTICE DESTINATION "${CMAKE_INSTALL_DATADIR}/licenses/kitten_text_processing")
set(config_dir "${CMAKE_INSTALL_LIBDIR}/cmake/KittenTextProcessing")
configure_package_config_file(cpp/cmake/KittenTextProcessingConfig.cmake.in
    "${CMAKE_CURRENT_BINARY_DIR}/KittenTextProcessingConfig.cmake"
    INSTALL_DESTINATION "${config_dir}" PATH_VARS KITTEN_INSTALL_DATA_DIR)
write_basic_package_version_file("${CMAKE_CURRENT_BINARY_DIR}/KittenTextProcessingConfigVersion.cmake"
    VERSION ${PROJECT_VERSION} COMPATIBILITY SameMajorVersion)
install(EXPORT KittenTextProcessingTargets NAMESPACE KittenTextProcessing:: DESTINATION "${config_dir}")
install(FILES "${CMAKE_CURRENT_BINARY_DIR}/KittenTextProcessingConfig.cmake"
              "${CMAKE_CURRENT_BINARY_DIR}/KittenTextProcessingConfigVersion.cmake" DESTINATION "${config_dir}")

if(BUILD_TESTING)
    add_executable(kitten-graph-test-driver cpp/tests/graph_driver.cpp)
    target_include_directories(kitten-graph-test-driver PRIVATE cpp/src)
    target_link_libraries(kitten-graph-test-driver PRIVATE KittenTextProcessing::normalizer)
    find_package(Threads REQUIRED)
    add_executable(kitten-cpp-tests cpp/tests/api_test.cpp)
    target_link_libraries(kitten-cpp-tests PRIVATE KittenTextProcessing::normalizer Threads::Threads)
    add_test(NAME cpp.api COMMAND kitten-cpp-tests "${KITTEN_DATA_DIR}")
    find_package(Python3 3.10 QUIET COMPONENTS Interpreter)
    if(Python3_FOUND AND KITTEN_BUILD_CLI)
        add_test(NAME cpp.shared_decoder COMMAND "${Python3_EXECUTABLE}" -S
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/check_cpp_decoder.py"
            --binary $<TARGET_FILE:kitten-graph-test-driver>)
        add_test(NAME cpp.shared_corpus COMMAND "${Python3_EXECUTABLE}" -S
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/check_cpp.py"
            --binary $<TARGET_FILE:kitten-normalize-cpp> --data "${KITTEN_DATA_DIR}" --backend cpp)
        set_tests_properties(cpp.shared_corpus PROPERTIES TIMEOUT 1200)
    endif()
endif()
