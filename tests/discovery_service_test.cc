#include "discovery_service.h"

#include <arpa/inet.h>
#include <cassert>
#include <cstring>
#include <iostream>
#include <netinet/in.h>
#include <string>
#include <sys/socket.h>
#include <sys/time.h>
#include <unistd.h>

static uint32_t active_sessions(void *)
{
    return 1;
}

int main()
{
    discovery_service_config_t config;
    config.discovery_port = 55052;
    config.grpc_port = 50051;
    config.model_name = "yolov5";
    config.task = "object_detection";
    config.active_sessions = active_sessions;
    config.active_sessions_context = NULL;

    discovery_service_t *service = NULL;
    assert(discovery_service_start(&config, &service) == 0);

    int client = socket(AF_INET, SOCK_DGRAM, 0);
    assert(client >= 0);
    struct timeval timeout = {2, 0};
    setsockopt(client, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));

    struct sockaddr_in address;
    std::memset(&address, 0, sizeof(address));
    address.sin_family = AF_INET;
    address.sin_port = htons(config.discovery_port);
    address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    const char request[] = "LUCKFOX_RKNN_DISCOVER";
    assert(sendto(client, request, sizeof(request) - 1, 0,
                  (struct sockaddr *)&address, sizeof(address)) > 0);

    char response[2048];
    ssize_t size = recvfrom(client, response, sizeof(response) - 1, 0, NULL, NULL);
    assert(size > 0);
    response[size] = '\0';
    std::string json(response);
    assert(json.find("\"service\":\"luckfox-rknn\"") != std::string::npos);
    assert(json.find("\"grpc_port\":50051") != std::string::npos);
    assert(json.find("\"model_name\":\"yolov5\"") != std::string::npos);
    assert(json.find("\"busy\":true") != std::string::npos);
    assert(json.find("\"password_required\":true") != std::string::npos);

    close(client);
    discovery_service_stop(service);
    std::cout << "discovery_service_test passed\n";
    return 0;
}