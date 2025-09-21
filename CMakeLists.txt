cmake_minimum_required(VERSION 3.16)
project(ALAI LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 11)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

include(FetchContent)

set(GGWAVE_BUILD_TESTS OFF CACHE BOOL "Disable ggwave tests" FORCE)
set(GGWAVE_BUILD_EXAMPLES ON CACHE BOOL "Enable ggwave examples" FORCE)
set(GGWAVE_SUPPORT_SDL2 OFF CACHE BOOL "Disable SDL2 dependency" FORCE)

FetchContent_Declare(
    ggwave
    GIT_REPOSITORY https://github.com/ggerganov/ggwave.git
    GIT_TAG ggwave-v0.4.1
)

FetchContent_MakeAvailable(ggwave)

add_custom_target(ggwave-cli ALL
    DEPENDS ggwave-to-file ggwave-from-file)
