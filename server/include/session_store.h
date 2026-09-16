#ifndef LUCKFOX_SESSION_STORE_H
#define LUCKFOX_SESSION_STORE_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define SESSION_ID_SIZE 65
#define SESSION_MODEL_SIZE 64

typedef struct session_store session_store_t;

typedef struct {
    uint32_t max_sessions;
    uint32_t idle_timeout_seconds;
} session_store_config_t;

int session_store_create(const session_store_config_t *config,
                         session_store_t **store);

int session_store_open(session_store_t *store,
                       const char *model_name,
                       char *session_id,
                       size_t session_id_size);

int session_store_validate(session_store_t *store,
                           const char *session_id,
                           char *model_name,
                           size_t model_name_size);

int session_store_close(session_store_t *store, const char *session_id);
uint32_t session_store_count(session_store_t *store);
void session_store_destroy(session_store_t *store);

#ifdef __cplusplus
}
#endif

#endif