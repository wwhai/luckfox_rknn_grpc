#include "session_store.h"

#include <chrono>
#include <cstdio>
#include <cstring>
#include <mutex>
#include <random>
#include <string>
#include <unordered_map>

typedef struct {
    std::string model_name;
    std::chrono::steady_clock::time_point last_access;
} session_entry_t;

struct session_store {
    uint32_t max_sessions;
    uint32_t idle_timeout_seconds;
    std::mutex mutex;
    std::unordered_map<std::string, session_entry_t> sessions;
    std::mt19937_64 random;
};

static void session_store_prune_locked(session_store_t *store)
{
    const std::chrono::steady_clock::time_point now = std::chrono::steady_clock::now();
    std::unordered_map<std::string, session_entry_t>::iterator it = store->sessions.begin();
    while (it != store->sessions.end()) {
        const uint64_t idle_seconds = (uint64_t)std::chrono::duration_cast<std::chrono::seconds>(
            now - it->second.last_access).count();
        if (idle_seconds >= store->idle_timeout_seconds) {
            it = store->sessions.erase(it);
        } else {
            ++it;
        }
    }
}

static std::string session_store_new_id(session_store_t *store)
{
    char buffer[SESSION_ID_SIZE];
    std::snprintf(buffer, sizeof(buffer), "%016llx%016llx",
                  (unsigned long long)store->random(),
                  (unsigned long long)store->random());
    return std::string(buffer);
}

int session_store_create(const session_store_config_t *config, session_store_t **store)
{
    if (config == NULL || store == NULL || config->max_sessions == 0 ||
        config->idle_timeout_seconds == 0) {
        return -1;
    }

    session_store_t *value = new session_store_t();
    value->max_sessions = config->max_sessions;
    value->idle_timeout_seconds = config->idle_timeout_seconds;
    value->random.seed((uint64_t)std::chrono::high_resolution_clock::now().time_since_epoch().count());
    *store = value;
    return 0;
}

int session_store_open(session_store_t *store, const char *model_name,
                       char *session_id, size_t session_id_size)
{
    if (store == NULL || model_name == NULL || session_id == NULL || session_id_size < 33) {
        return -1;
    }

    std::lock_guard<std::mutex> lock(store->mutex);
    session_store_prune_locked(store);
    if (store->sessions.size() >= store->max_sessions) {
        return -2;
    }

    std::string id;
    do {
        id = session_store_new_id(store);
    } while (store->sessions.find(id) != store->sessions.end());

    session_entry_t entry;
    entry.model_name = model_name;
    entry.last_access = std::chrono::steady_clock::now();
    store->sessions[id] = entry;
    std::snprintf(session_id, session_id_size, "%s", id.c_str());
    return 0;
}

int session_store_validate(session_store_t *store, const char *session_id,
                           char *model_name, size_t model_name_size)
{
    if (store == NULL || session_id == NULL || model_name == NULL || model_name_size == 0) {
        return -1;
    }

    std::lock_guard<std::mutex> lock(store->mutex);
    session_store_prune_locked(store);
    std::unordered_map<std::string, session_entry_t>::iterator it = store->sessions.find(session_id);
    if (it == store->sessions.end()) {
        return -2;
    }

    it->second.last_access = std::chrono::steady_clock::now();
    std::snprintf(model_name, model_name_size, "%s", it->second.model_name.c_str());
    return 0;
}

int session_store_close(session_store_t *store, const char *session_id)
{
    if (store == NULL || session_id == NULL) {
        return -1;
    }
    std::lock_guard<std::mutex> lock(store->mutex);
    return store->sessions.erase(session_id) == 1 ? 0 : -2;
}

uint32_t session_store_count(session_store_t *store)
{
    if (store == NULL) {
        return 0;
    }
    std::lock_guard<std::mutex> lock(store->mutex);
    session_store_prune_locked(store);
    return (uint32_t)store->sessions.size();
}

void session_store_destroy(session_store_t *store)
{
    delete store;
}