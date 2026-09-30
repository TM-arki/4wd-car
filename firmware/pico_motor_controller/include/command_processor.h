#pragma once

#include <stddef.h>
#include <stdint.h>

void command_print_help(void);
void command_handle_line(char *line, uint32_t now_ms);
