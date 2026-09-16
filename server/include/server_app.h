#ifndef LUCKFOX_SERVER_APP_H
#define LUCKFOX_SERVER_APP_H

#include <stdint.h>

typedef struct {
    const char *listen_address;
    const char *model_path;
    const char *password;
    uint32_t max_image_bytes;
    uint32_t idle_timeout_seconds;
} server_options_t;

int server_run(const server_options_t *options);

#endif