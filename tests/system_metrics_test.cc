#include "system_metrics.h"

#include <cassert>
#include <iostream>

int main()
{
    system_metrics_sampler_t *sampler = NULL;
    assert(system_metrics_sampler_create(&sampler) == 0);

    system_metrics_t metrics;
    assert(system_metrics_read(sampler, &metrics) == 0);
    assert(metrics.cpu_core_count >= 1);
    assert(metrics.cpu_usage_percent >= 0.0 && metrics.cpu_usage_percent <= 100.0);
    assert(metrics.load_average_1m >= 0.0);
    assert(metrics.memory_total_bytes > 0);
    assert(metrics.memory_available_bytes <= metrics.memory_total_bytes);
    assert(metrics.memory_usage_percent >= 0.0 && metrics.memory_usage_percent <= 100.0);
    assert(metrics.uptime_seconds > 0);

    system_metrics_sampler_destroy(sampler);
    std::cout << "system_metrics_test passed\n";
    return 0;
}