cmake_minimum_required(VERSION 3.13)

if(EXISTS ${CMAKE_CURRENT_LIST_DIR}/pico_sdk_import.cmake)
    include(${CMAKE_CURRENT_LIST_DIR}/pico_sdk_import.cmake)
elseif(DEFINED ENV{PICO_SDK_PATH})
    include($ENV{PICO_SDK_PATH}/external/pico_sdk_import.cmake)
else()
    message(FATAL_ERROR "Pico SDK not found. Set PICO_SDK_PATH or copy pico_sdk_import.cmake into this folder.")
endif()

project(pico_motor_controller C CXX ASM)
set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)

pico_sdk_init()

add_executable(pico_motor_controller
    src/main.cpp
)

target_include_directories(pico_motor_controller PRIVATE
    include
)

target_link_libraries(pico_motor_controller
    pico_stdlib
    hardware_pwm
)

pico_enable_stdio_usb(pico_motor_controller 1)
pico_enable_stdio_uart(pico_motor_controller 0)

pico_add_extra_outputs(pico_motor_controller)
