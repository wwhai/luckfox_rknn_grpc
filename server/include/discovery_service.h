#ifndef LUCKFOX_DISCOVERY_SERVICE_H
#define LUCKFOX_DISCOVERY_SERVICE_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define DISCOVERY_DEFAULT_PORT 50052

typedef struct discovery_service discovery_service_t;
typedef uint32_t (*discovery_active_sessions_fn)(void *context);

typedef struct {
    uint16_t discovery_port;
    uint16_t grpc_port;
    const char *model_name;
    const char *task;
    discovery_active_sessions_fn active_sessions;
    void *active_sessions_context;
} discovery_service_config_t;

int discovery_service_start(const discovery_service_config_t *config,
                            discovery_service_t **service);
void discovery_service_stop(discovery_service_t *service);

#ifdef __cplusplus
}
#endif

#endif