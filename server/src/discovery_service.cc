#include "discovery_service.h"

#include <arpa/inet.h>
#include <atomic>
#include <cstdio>
#include <cstring>
#include <netinet/in.h>
#include <string>
#include <sys/socket.h>
#include <sys/time.h>
#include <sys/utsname.h>
#include <thread>
#include <unistd.h>

#define DISCOVERY_REQUEST "LUCKFOX_RKNN_DISCOVER"

struct discovery_service {
    int socket_fd;
    uint16_t grpc_port;
    std::string model_name;
    std::string task;
    discovery_active_sessions_fn active_sessions;
    void *active_sessions_context;
    std::atomic<bool> stopping;
    std::thread worker;
};

static std::string json_escape(const char *value)
{
    std::string escaped;
    for (const unsigned char *cursor = (const unsigned char *)value; *cursor != '\0'; ++cursor) {
        if (*cursor == '"' || *cursor == '\\') {
            escaped.push_back('\\');
            escaped.push_back((char)*cursor);
        } else if (*cursor >= 0x20) {
            escaped.push_back((char)*cursor);
        }
    }
    return escaped;
}

static std::string discovery_response(discovery_service_t *service)
{
    char hostname[128] = "unknown";
    gethostname(hostname, sizeof(hostname) - 1);
    struct utsname system_info;
    const char *architecture = uname(&system_info) == 0 ? system_info.machine : "arm32";
    uint32_t active_sessions = service->active_sessions == NULL
        ? 0 : service->active_sessions(service->active_sessions_context);

    char response[1024];
    std::snprintf(
        response,
        sizeof(response),
        "{\"service\":\"luckfox-rknn\",\"hostname\":\"%s\","
        "\"board_model\":\"Luckfox Pico\",\"soc\":\"Rockchip RV1106/RV1103\","
        "\"architecture\":\"%s\",\"grpc_port\":%u,\"model_name\":\"%s\","
        "\"task\":\"%s\",\"busy\":%s,\"password_required\":true}",
        json_escape(hostname).c_str(),
        json_escape(architecture).c_str(),
        service->grpc_port,
        json_escape(service->model_name.c_str()).c_str(),
        json_escape(service->task.c_str()).c_str(),
        active_sessions == 0 ? "false" : "true");
    return std::string(response);
}

static void discovery_loop(discovery_service_t *service)
{
    char request[128];
    while (!service->stopping.load()) {
        struct sockaddr_in client_address;
        socklen_t client_size = sizeof(client_address);
        ssize_t size = recvfrom(service->socket_fd, request, sizeof(request) - 1, 0,
                                (struct sockaddr *)&client_address, &client_size);
        if (size <= 0) {
            continue;
        }
        request[size] = '\0';
        if (std::strcmp(request, DISCOVERY_REQUEST) != 0) {
            continue;
        }
        std::string response = discovery_response(service);
        sendto(service->socket_fd, response.data(), response.size(), 0,
               (struct sockaddr *)&client_address, client_size);
    }
}

int discovery_service_start(const discovery_service_config_t *config,
                            discovery_service_t **service)
{
    if (config == NULL || service == NULL || config->discovery_port == 0 ||
        config->grpc_port == 0 || config->model_name == NULL || config->task == NULL) {
        return -1;
    }

    int socket_fd = socket(AF_INET, SOCK_DGRAM, 0);
    if (socket_fd < 0) {
        return -2;
    }
    int enabled = 1;
    setsockopt(socket_fd, SOL_SOCKET, SO_REUSEADDR, &enabled, sizeof(enabled));
    struct timeval timeout = {1, 0};
    setsockopt(socket_fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));

    struct sockaddr_in address;
    std::memset(&address, 0, sizeof(address));
    address.sin_family = AF_INET;
    address.sin_addr.s_addr = htonl(INADDR_ANY);
    address.sin_port = htons(config->discovery_port);
    if (bind(socket_fd, (struct sockaddr *)&address, sizeof(address)) != 0) {
        close(socket_fd);
        return -3;
    }

    discovery_service_t *value = new discovery_service_t();
    value->socket_fd = socket_fd;
    value->grpc_port = config->grpc_port;
    value->model_name = config->model_name;
    value->task = config->task;
    value->active_sessions = config->active_sessions;
    value->active_sessions_context = config->active_sessions_context;
    value->stopping.store(false);
    value->worker = std::thread(discovery_loop, value);
    *service = value;
    return 0;
}

void discovery_service_stop(discovery_service_t *service)
{
    if (service == NULL) {
        return;
    }
    service->stopping.store(true);
    shutdown(service->socket_fd, SHUT_RDWR);
    close(service->socket_fd);
    if (service->worker.joinable()) {
        service->worker.join();
    }
    delete service;
}