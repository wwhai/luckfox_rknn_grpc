#include "system_metrics.h"

#include <cstdio>
#include <cstring>
#include <mutex>
#include <new>
#include <unistd.h>

typedef struct {
    uint64_t idle;
    uint64_t total;
} cpu_times_t;

struct system_metrics_sampler {
    std::mutex lock;
    cpu_times_t previous_cpu;
    bool has_previous_cpu;
};

static int read_cpu_times(cpu_times_t *times)
{
    FILE *file = std::fopen("/proc/stat", "r");
    if (file == NULL) {
        return -1;
    }
    unsigned long long user = 0;
    unsigned long long nice = 0;
    unsigned long long system = 0;
    unsigned long long idle = 0;
    unsigned long long io_wait = 0;
    unsigned long long irq = 0;
    unsigned long long soft_irq = 0;
    unsigned long long steal = 0;
    int count = std::fscanf(file, "cpu %llu %llu %llu %llu %llu %llu %llu %llu",
                            &user, &nice, &system, &idle, &io_wait, &irq, &soft_irq, &steal);
    std::fclose(file);
    if (count < 4) {
        return -1;
    }
    times->idle = idle + io_wait;
    times->total = user + nice + system + idle + io_wait + irq + soft_irq + steal;
    return 0;
}

static int read_memory(system_metrics_t *metrics)
{
    FILE *file = std::fopen("/proc/meminfo", "r");
    if (file == NULL) {
        return -1;
    }
    unsigned long long total_kb = 0;
    unsigned long long available_kb = 0;
    unsigned long long free_kb = 0;
    unsigned long long buffers_kb = 0;
    unsigned long long cached_kb = 0;
    char key[64];
    unsigned long long value = 0;
    while (std::fscanf(file, "%63s %llu kB", key, &value) == 2) {
        if (std::strcmp(key, "MemTotal:") == 0) {
            total_kb = value;
        } else if (std::strcmp(key, "MemAvailable:") == 0) {
            available_kb = value;
        } else if (std::strcmp(key, "MemFree:") == 0) {
            free_kb = value;
        } else if (std::strcmp(key, "Buffers:") == 0) {
            buffers_kb = value;
        } else if (std::strcmp(key, "Cached:") == 0) {
            cached_kb = value;
        }
    }
    std::fclose(file);
    if (total_kb == 0) {
        return -1;
    }
    if (available_kb == 0) {
        available_kb = free_kb + buffers_kb + cached_kb;
    }
    if (available_kb > total_kb) {
        available_kb = total_kb;
    }
    metrics->memory_total_bytes = total_kb * 1024ULL;
    metrics->memory_available_bytes = available_kb * 1024ULL;
    metrics->memory_usage_percent =
        100.0 * (double)(total_kb - available_kb) / (double)total_kb;
    return 0;
}

static int read_load_average(system_metrics_t *metrics)
{
    FILE *file = std::fopen("/proc/loadavg", "r");
    if (file == NULL) {
        return -1;
    }
    int count = std::fscanf(file, "%lf %lf %lf", &metrics->load_average_1m,
                            &metrics->load_average_5m, &metrics->load_average_15m);
    std::fclose(file);
    return count == 3 ? 0 : -1;
}

static int read_uptime(system_metrics_t *metrics)
{
    FILE *file = std::fopen("/proc/uptime", "r");
    if (file == NULL) {
        return -1;
    }
    double uptime = 0.0;
    int count = std::fscanf(file, "%lf", &uptime);
    std::fclose(file);
    if (count != 1 || uptime < 0.0) {
        return -1;
    }
    metrics->uptime_seconds = (uint64_t)uptime;
    return 0;
}

static void read_temperature(system_metrics_t *metrics)
{
    for (int zone = 0; zone < 8; ++zone) {
        char path[128];
        std::snprintf(path, sizeof(path), "/sys/class/thermal/thermal_zone%d/temp", zone);
        FILE *file = std::fopen(path, "r");
        if (file == NULL) {
            continue;
        }
        double value = 0.0;
        int count = std::fscanf(file, "%lf", &value);
        std::fclose(file);
        if (count == 1) {
            metrics->temperature_available = 1;
            metrics->temperature_celsius = value > 1000.0 ? value / 1000.0 : value;
            return;
        }
    }
}

int system_metrics_sampler_create(system_metrics_sampler_t **sampler)
{
    if (sampler == NULL) {
        return -1;
    }
    system_metrics_sampler_t *value = new (std::nothrow) system_metrics_sampler_t();
    if (value == NULL) {
        return -2;
    }
    value->has_previous_cpu = read_cpu_times(&value->previous_cpu) == 0;
    *sampler = value;
    return 0;
}

int system_metrics_read(system_metrics_sampler_t *sampler, system_metrics_t *metrics)
{
    if (sampler == NULL || metrics == NULL) {
        return -1;
    }
    std::memset(metrics, 0, sizeof(*metrics));
    long core_count = sysconf(_SC_NPROCESSORS_ONLN);
    metrics->cpu_core_count = core_count > 0 ? (uint32_t)core_count : 1;

    cpu_times_t current_cpu;
    {
        std::lock_guard<std::mutex> guard(sampler->lock);
        if (read_cpu_times(&current_cpu) != 0) {
            return -2;
        }
        if (sampler->has_previous_cpu && current_cpu.total > sampler->previous_cpu.total) {
            uint64_t total_delta = current_cpu.total - sampler->previous_cpu.total;
            uint64_t idle_delta = current_cpu.idle - sampler->previous_cpu.idle;
            metrics->cpu_usage_percent = 100.0 * (double)(total_delta - idle_delta) /
                                         (double)total_delta;
        }
        sampler->previous_cpu = current_cpu;
        sampler->has_previous_cpu = true;
    }

    if (read_memory(metrics) != 0 || read_load_average(metrics) != 0 ||
        read_uptime(metrics) != 0) {
        return -3;
    }
    read_temperature(metrics);
    return 0;
}

void system_metrics_sampler_destroy(system_metrics_sampler_t *sampler)
{
    delete sampler;
}