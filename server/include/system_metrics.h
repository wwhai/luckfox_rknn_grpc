#ifndef LUCKFOX_SYSTEM_METRICS_H
#define LUCKFOX_SYSTEM_METRICS_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct system_metrics_sampler system_metrics_sampler_t;

typedef struct {
    uint32_t cpu_core_count;
    double cpu_usage_percent;
    double load_average_1m;
    double load_average_5m;
    double load_average_15m;
    uint64_t memory_total_bytes;
    uint64_t memory_available_bytes;
    double memory_usage_percent;
    uint64_t uptime_seconds;
    int temperature_available;
    double temperature_celsius;
} system_metrics_t;

int system_metrics_sampler_create(system_metrics_sampler_t **sampler);
int system_metrics_read(system_metrics_sampler_t *sampler, system_metrics_t *metrics);
void system_metrics_sampler_destroy(system_metrics_sampler_t *sampler);

#ifdef __cplusplus
}
#endif

#endif