#include "server_app.h"

#include <csignal>
#include <cstdio>
#include <cstring>
#include <memory>
#include <string>
#include <sys/stat.h>
#include <sys/utsname.h>
#include <thread>
#include <unistd.h>

#include <grpcpp/grpcpp.h>

#include "accelerator_engine.h"
#include "discovery_service.h"
#include "rknn_accelerator.grpc.pb.h"
#include "session_store.h"
#include "system_metrics.h"

namespace api = luckfox::rknn;

typedef struct {
    accelerator_engine_t *engine;
    session_store_t *sessions;
    system_metrics_sampler_t *metrics;
    const server_options_t *options;
} service_context_t;

static uint32_t active_session_count(void *context)
{
    return session_store_count((session_store_t *)context);
}

static std::string read_text_file(const char *path)
{
    FILE *file = std::fopen(path, "rb");
    if (file == NULL) {
        return "";
    }
    char buffer[256];
    size_t size = std::fread(buffer, 1, sizeof(buffer) - 1, file);
    std::fclose(file);
    while (size > 0 && (buffer[size - 1] == '\0' || buffer[size - 1] == '\n' ||
                        buffer[size - 1] == '\r' || buffer[size - 1] == ' ')) {
        --size;
    }
    buffer[size] = '\0';
    return std::string(buffer);
}

static void fill_board_info(api::BoardInfo *board)
{
    char hostname[128] = "unknown";
    if (gethostname(hostname, sizeof(hostname) - 1) != 0) {
        std::snprintf(hostname, sizeof(hostname), "%s", "unknown");
    }
    board->set_hostname(hostname);

    std::string board_model = read_text_file("/proc/device-tree/model");
    board->set_board_model(board_model.empty() ? "Luckfox Pico" : board_model);
    board->set_soc("Rockchip RV1106/RV1103");

    struct utsname system_info;
    if (uname(&system_info) == 0) {
        board->set_operating_system(std::string(system_info.sysname) + " " + system_info.release);
        board->set_architecture(system_info.machine);
    } else {
        board->set_operating_system("Linux/uClibc");
        board->set_architecture("arm32");
    }
}

static void fill_model_info(service_context_t *context, api::ModelInfo *model)
{
    model->set_name("yolov5");
    model->set_task("object_detection");
    model->set_input_width(640);
    model->set_input_height(640);
    model->add_accepted_encodings(api::IMAGE_ENCODING_JPEG);
    model->add_accepted_encodings(api::IMAGE_ENCODING_PNG);
    model->set_quantization("INT8 affine asymmetric");
    model->set_tensor_layout("NHWC");
    struct stat model_stat;
    if (stat(context->options->model_path, &model_stat) == 0) {
        model->set_file_size_bytes((uint64_t)model_stat.st_size);
    }
}

static grpc::Status validate_session(service_context_t *context,
                                     const std::string &session_id)
{
    char model_name[SESSION_MODEL_SIZE];
    int result = session_store_validate(context->sessions, session_id.c_str(),
                                        model_name, sizeof(model_name));
    if (result != 0) {
        return grpc::Status(grpc::StatusCode::NOT_FOUND,
                            "session does not exist or has expired");
    }
    if (std::strcmp(model_name, "yolov5") != 0) {
        return grpc::Status(grpc::StatusCode::FAILED_PRECONDITION,
                            "session model is unavailable");
    }
    return grpc::Status::OK;
}

static grpc::Status run_inference(service_context_t *context,
                                  const api::InferRequest *request,
                                  api::InferResponse *response)
{
    grpc::Status session_status = validate_session(context, request->session_id());
    if (!session_status.ok()) {
        return session_status;
    }
    if (request->image().empty()) {
        return grpc::Status(grpc::StatusCode::INVALID_ARGUMENT, "image is empty");
    }
    if (request->image().size() > context->options->max_image_bytes) {
        return grpc::Status(grpc::StatusCode::RESOURCE_EXHAUSTED,
                            "image exceeds max_image_bytes");
    }
    if (request->encoding() != api::IMAGE_ENCODING_JPEG &&
        request->encoding() != api::IMAGE_ENCODING_PNG) {
        return grpc::Status(grpc::StatusCode::INVALID_ARGUMENT,
                            "encoding must be JPEG or PNG");
    }

    accelerator_infer_options_t options;
    options.score_threshold = request->options().score_threshold();
    options.nms_threshold = request->options().nms_threshold();
    options.max_detections = request->options().max_detections();

    accelerator_result_t result;
    char error[256];
    int infer_result = accelerator_engine_infer(
        context->engine,
        (const uint8_t *)request->image().data(),
        request->image().size(),
        &options,
        &result,
        error,
        sizeof(error));
    if (infer_result == -2) {
        return grpc::Status(grpc::StatusCode::INVALID_ARGUMENT, error);
    }
    if (infer_result != 0) {
        return grpc::Status(grpc::StatusCode::INTERNAL, error);
    }

    response->set_request_id(request->request_id());
    response->set_image_width(result.image_width);
    response->set_image_height(result.image_height);
    for (uint32_t index = 0; index < result.detection_count; ++index) {
        const accelerator_detection_t *source = &result.detections[index];
        api::Detection *target = response->add_detections();
        target->set_sequence_number(index + 1);
        target->set_class_id(source->class_id);
        target->set_label(source->label);
        target->set_score(source->score);
        target->mutable_box()->set_left(source->left);
        target->mutable_box()->set_top(source->top);
        target->mutable_box()->set_right(source->right);
        target->mutable_box()->set_bottom(source->bottom);
    }
    response->mutable_timing()->set_queue_us(result.queue_us);
    response->mutable_timing()->set_decode_us(result.decode_us);
    response->mutable_timing()->set_inference_us(result.inference_us);
    response->mutable_timing()->set_total_us(result.total_us);
    return grpc::Status::OK;
}

class RknnAcceleratorService final : public api::RknnAccelerator::Service {
public:
    explicit RknnAcceleratorService(service_context_t *context) : context_(context) {}

    grpc::Status GetServerInfo(grpc::ServerContext *, const api::ServerInfoRequest *,
                               api::ServerInfoResponse *response) override
    {
        response->set_device("Luckfox Pico RV1106/RV1103");
        fill_board_info(response->mutable_board());
        fill_model_info(context_, response->add_models());
        response->set_max_image_bytes(context_->options->max_image_bytes);
        response->set_max_sessions(1);
        response->set_exclusive_access(true);
        return grpc::Status::OK;
    }

    grpc::Status Health(grpc::ServerContext *, const api::HealthRequest *,
                        api::HealthResponse *response) override
    {
        response->set_status(api::SERVING_STATUS_SERVING);
        response->set_active_sessions(session_store_count(context_->sessions));
        response->set_queued_requests(accelerator_engine_queue_depth(context_->engine));
        response->set_message("ready");
        return grpc::Status::OK;
    }

    grpc::Status GetPerformance(grpc::ServerContext *, const api::PerformanceRequest *,
                                api::PerformanceResponse *response) override
    {
        system_metrics_t metrics;
        if (system_metrics_read(context_->metrics, &metrics) != 0) {
            return grpc::Status(grpc::StatusCode::INTERNAL,
                                "failed to read system performance metrics");
        }
        response->set_cpu_core_count(metrics.cpu_core_count);
        response->set_cpu_usage_percent(metrics.cpu_usage_percent);
        response->set_load_average_1m(metrics.load_average_1m);
        response->set_load_average_5m(metrics.load_average_5m);
        response->set_load_average_15m(metrics.load_average_15m);
        response->set_memory_total_bytes(metrics.memory_total_bytes);
        response->set_memory_available_bytes(metrics.memory_available_bytes);
        response->set_memory_usage_percent(metrics.memory_usage_percent);
        response->set_uptime_seconds(metrics.uptime_seconds);
        response->set_temperature_available(metrics.temperature_available != 0);
        response->set_temperature_celsius(metrics.temperature_celsius);
        return grpc::Status::OK;
    }

    grpc::Status OpenSession(grpc::ServerContext *, const api::OpenSessionRequest *request,
                             api::OpenSessionResponse *response) override
    {
        if (request->model_name() != "yolov5") {
            return grpc::Status(grpc::StatusCode::NOT_FOUND, "model is not available");
        }
        if (request->password() != context_->options->password) {
            return grpc::Status(grpc::StatusCode::UNAUTHENTICATED, "invalid password");
        }

        char session_id[SESSION_ID_SIZE];
        int result = session_store_open(context_->sessions, request->model_name().c_str(),
                                        session_id, sizeof(session_id));
        if (result == -2) {
            return grpc::Status(grpc::StatusCode::RESOURCE_EXHAUSTED,
                                "accelerator is already connected to another client");
        }
        if (result != 0) {
            return grpc::Status(grpc::StatusCode::INTERNAL, "failed to create session");
        }

        response->set_session_id(session_id);
        response->set_idle_timeout_seconds(context_->options->idle_timeout_seconds);
        fill_model_info(context_, response->mutable_model());
        return grpc::Status::OK;
    }

    grpc::Status Infer(grpc::ServerContext *, const api::InferRequest *request,
                       api::InferResponse *response) override
    {
        return run_inference(context_, request, response);
    }

    grpc::Status StreamInfer(grpc::ServerContext *,
                             grpc::ServerReaderWriter<api::InferResponse, api::InferRequest> *stream) override
    {
        api::InferRequest request;
        while (stream->Read(&request)) {
            api::InferResponse response;
            grpc::Status status = run_inference(context_, &request, &response);
            if (!status.ok()) {
                return status;
            }
            if (!stream->Write(response)) {
                break;
            }
        }
        return grpc::Status::OK;
    }

    grpc::Status CloseSession(grpc::ServerContext *, const api::CloseSessionRequest *request,
                              api::CloseSessionResponse *response) override
    {
        int result = session_store_close(context_->sessions, request->session_id().c_str());
        response->set_closed(result == 0);
        return grpc::Status::OK;
    }

private:
    service_context_t *context_;
};

int server_run(const server_options_t *options)
{
    if (options == NULL || options->listen_address == NULL || options->model_path == NULL) {
        std::fprintf(stderr, "invalid server options\n");
        return 2;
    }

    accelerator_engine_config_t engine_config;
    engine_config.model_path = options->model_path;
    engine_config.default_score_threshold = 0.25f;
    engine_config.default_nms_threshold = 0.45f;

    accelerator_engine_t *engine = NULL;
    char error[256];
    if (accelerator_engine_create(&engine_config, &engine, error, sizeof(error)) != 0) {
        std::fprintf(stderr, "engine startup failed: %s\n", error);
        return 3;
    }

    session_store_config_t session_config;
    session_config.max_sessions = 1;
    session_config.idle_timeout_seconds = options->idle_timeout_seconds;
    session_store_t *sessions = NULL;
    if (session_store_create(&session_config, &sessions) != 0) {
        std::fprintf(stderr, "session store startup failed\n");
        accelerator_engine_destroy(engine);
        return 4;
    }

    system_metrics_sampler_t *metrics = NULL;
    if (system_metrics_sampler_create(&metrics) != 0) {
        std::fprintf(stderr, "performance sampler startup failed\n");
        session_store_destroy(sessions);
        accelerator_engine_destroy(engine);
        return 5;
    }

    service_context_t context;
    context.engine = engine;
    context.sessions = sessions;
    context.metrics = metrics;
    context.options = options;
    RknnAcceleratorService service(&context);

    sigset_t signals;
    sigemptyset(&signals);
    sigaddset(&signals, SIGINT);
    sigaddset(&signals, SIGTERM);
    pthread_sigmask(SIG_BLOCK, &signals, NULL);

    grpc::ServerBuilder builder;
    int selected_port = 0;
    builder.AddListeningPort(options->listen_address, grpc::InsecureServerCredentials(),
                             &selected_port);
    builder.SetMaxReceiveMessageSize((int)options->max_image_bytes + 4096);
    builder.RegisterService(&service);
    std::unique_ptr<grpc::Server> server(builder.BuildAndStart());
    if (server.get() == NULL || selected_port == 0) {
        std::fprintf(stderr, "failed to listen on %s\n", options->listen_address);
        system_metrics_sampler_destroy(metrics);
        session_store_destroy(sessions);
        accelerator_engine_destroy(engine);
        return 5;
    }

    discovery_service_config_t discovery_config;
    discovery_config.discovery_port = DISCOVERY_DEFAULT_PORT;
    discovery_config.grpc_port = (uint16_t)selected_port;
    discovery_config.model_name = "yolov5";
    discovery_config.task = "object_detection";
    discovery_config.active_sessions = active_session_count;
    discovery_config.active_sessions_context = sessions;
    discovery_service_t *discovery = NULL;
    if (discovery_service_start(&discovery_config, &discovery) != 0) {
        std::fprintf(stderr, "failed to start UDP discovery on port %u\n",
                     (unsigned int)DISCOVERY_DEFAULT_PORT);
        server->Shutdown();
        system_metrics_sampler_destroy(metrics);
        session_store_destroy(sessions);
        accelerator_engine_destroy(engine);
        return 6;
    }

    std::printf("RKNN gRPC server listening on %s; discovery UDP %u\n",
                options->listen_address, (unsigned int)DISCOVERY_DEFAULT_PORT);
    std::thread signal_thread([&server, &signals]() {
        int signal_number = 0;
        sigwait(&signals, &signal_number);
        server->Shutdown();
    });
    server->Wait();
    signal_thread.join();

    discovery_service_stop(discovery);
    system_metrics_sampler_destroy(metrics);
    session_store_destroy(sessions);
    accelerator_engine_destroy(engine);
    return 0;
}