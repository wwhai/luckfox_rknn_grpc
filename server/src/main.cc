#include "server_app.h"

#include <cstdio>
#include <cstdlib>
#include <cstring>

static void print_usage(const char *program)
{
    std::printf(
        "Usage: %s [options]\n"
        "  --listen ADDRESS          Listen address (default 0.0.0.0:50051)\n"
        "  --model PATH              RKNN model path (default ./model/yolov5.rknn)\n"
        "  --password PASSWORD       Connection password (default 19940724)\n"
        "  --max-image-bytes N       Maximum encoded image size (default 8388608)\n"
        "  --session-timeout N       Idle timeout in seconds (default 300)\n"
        "  --help                    Show this help\n",
        program);
}

static int parse_uint32(const char *text, uint32_t *value)
{
    char *end = NULL;
    unsigned long parsed = std::strtoul(text, &end, 10);
    if (text[0] == '\0' || end == NULL || *end != '\0' || parsed == 0 || parsed > 0xffffffffUL) {
        return -1;
    }
    *value = (uint32_t)parsed;
    return 0;
}

int main(int argc, char **argv)
{
    server_options_t options;
    options.listen_address = "0.0.0.0:50051";
    options.model_path = "./model/yolov5.rknn";
    options.password = "19940724";
    options.max_image_bytes = 8U * 1024U * 1024U;
    options.idle_timeout_seconds = 300;

    for (int index = 1; index < argc; ++index) {
        if (std::strcmp(argv[index], "--help") == 0) {
            print_usage(argv[0]);
            return 0;
        }
        if (index + 1 >= argc) {
            std::fprintf(stderr, "missing value for %s\n", argv[index]);
            print_usage(argv[0]);
            return 2;
        }
        const char *name = argv[index++];
        const char *value = argv[index];
        if (std::strcmp(name, "--listen") == 0) {
            options.listen_address = value;
        } else if (std::strcmp(name, "--model") == 0) {
            options.model_path = value;
        } else if (std::strcmp(name, "--password") == 0) {
            options.password = value;
        } else if (std::strcmp(name, "--max-image-bytes") == 0) {
            if (parse_uint32(value, &options.max_image_bytes) != 0) return 2;
        } else if (std::strcmp(name, "--session-timeout") == 0) {
            if (parse_uint32(value, &options.idle_timeout_seconds) != 0) return 2;
        } else {
            std::fprintf(stderr, "unknown option: %s\n", name);
            print_usage(argv[0]);
            return 2;
        }
    }

    return server_run(&options);
}