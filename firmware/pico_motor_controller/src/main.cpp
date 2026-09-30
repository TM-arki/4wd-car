#include <stdio.h>

#include "command_processor.h"
#include "motor_controller.h"
#include "pico/stdlib.h"

int main(void) {
    stdio_init_all();
    motor_controller_init();

    sleep_ms(1500);
    puts("Pico motor controller ready. Type HELP.");

    char line[128];
    size_t length = 0;

    while (true) {
        const uint32_t now_ms = to_ms_since_boot(get_absolute_time());
        motor_controller_poll(now_ms);

        int ch = getchar_timeout_us(1000);
        if (ch == PICO_ERROR_TIMEOUT) {
            continue;
        }

        if (ch == '\r') {
            continue;
        }

        if (ch == '\n') {
            line[length] = '\0';
            command_handle_line(line, to_ms_since_boot(get_absolute_time()));
            length = 0;
            continue;
        }

        if (length < sizeof(line) - 1) {
            line[length++] = static_cast<char>(ch);
        } else {
            length = 0;
            motor_stop_all();
            puts("ERR Line too long. Motors stopped.");
        }
    }
}
