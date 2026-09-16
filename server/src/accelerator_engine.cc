#include "accelerator_engine.h"

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <mutex>
#include <vector>

#include "opencv2/core/core.hpp"
#include "opencv2/highgui/highgui.hpp"
#include "opencv2/imgproc/imgproc.hpp"
#include "yolov5.h"

struct accelerator_engine {
    rknn_app_context_t app;
    float default_score_threshold;
    float default_nms_threshold;
    std::mutex npu_mutex;
    std::atomic<uint32_t> waiting;
};

static uint64_t elapsed_us(std::chrono::steady_clock::time_point start,
                           std::chrono::steady_clock::time_point end)
{
    return (uint64_t)std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
}

static void set_error(char *error, size_t error_size, const char *message)
{
    if (error != NULL && error_size > 0) {
        std::snprintf(error, error_size, "%s", message);
    }
}

int accelerator_engine_create(const accelerator_engine_config_t *config,
                              accelerator_engine_t **engine,
                              char *error,
                              size_t error_size)
{
    if (config == NULL || engine == NULL || config->model_path == NULL) {
        set_error(error, error_size, "invalid engine configuration");
        return -1;
    }

    accelerator_engine_t *value = new accelerator_engine_t();
    std::memset(&value->app, 0, sizeof(value->app));
    value->default_score_threshold = config->default_score_threshold;
    value->default_nms_threshold = config->default_nms_threshold;
    value->waiting.store(0);

    if (init_yolov5_model(config->model_path, &value->app) != 0) {
        delete value;
        set_error(error, error_size, "failed to initialize RKNN model");
        return -2;
    }
    if (init_post_process() != 0) {
        accelerator_engine_destroy(value);
        set_error(error, error_size, "failed to load model labels");
        return -3;
    }

    *engine = value;
    return 0;
}

int accelerator_engine_infer(accelerator_engine_t *engine,
                             const uint8_t *encoded_image,
                             size_t encoded_image_size,
                             const accelerator_infer_options_t *options,
                             accelerator_result_t *result,
                             char *error,
                             size_t error_size)
{
    if (engine == NULL || encoded_image == NULL || encoded_image_size == 0 || result == NULL) {
        set_error(error, error_size, "invalid inference arguments");
        return -1;
    }

    std::memset(result, 0, sizeof(*result));
    const std::chrono::steady_clock::time_point total_start = std::chrono::steady_clock::now();
    cv::Mat encoded(1, (int)encoded_image_size, CV_8UC1, (void *)encoded_image);
    cv::Mat image = cv::imdecode(encoded, cv::IMREAD_COLOR);
    const std::chrono::steady_clock::time_point decode_end = std::chrono::steady_clock::now();
    if (image.empty()) {
        set_error(error, error_size, "image decode failed; expected JPEG or PNG");
        return -2;
    }

    result->image_width = (uint32_t)image.cols;
    result->image_height = (uint32_t)image.rows;
    const float score_threshold = options != NULL && options->score_threshold > 0.0f
        ? options->score_threshold : engine->default_score_threshold;
    const float nms_threshold = options != NULL && options->nms_threshold > 0.0f
        ? options->nms_threshold : engine->default_nms_threshold;
    uint32_t max_detections = options != NULL && options->max_detections > 0
        ? options->max_detections : ACCELERATOR_MAX_DETECTIONS;
    max_detections = std::min(max_detections, (uint32_t)ACCELERATOR_MAX_DETECTIONS);

    engine->waiting.fetch_add(1);
    const std::chrono::steady_clock::time_point queue_start = std::chrono::steady_clock::now();
    std::lock_guard<std::mutex> lock(engine->npu_mutex);
    const std::chrono::steady_clock::time_point queue_end = std::chrono::steady_clock::now();
    engine->waiting.fetch_sub(1);

    cv::Mat input(engine->app.model_height, engine->app.model_width, CV_8UC3,
                  engine->app.input_mems[0]->virt_addr);
    cv::resize(image, input, cv::Size(engine->app.model_width, engine->app.model_height),
               0, 0, cv::INTER_LINEAR);

    object_detect_result_list detections;
    std::memset(&detections, 0, sizeof(detections));
    const std::chrono::steady_clock::time_point inference_start = std::chrono::steady_clock::now();
    int run_result = rknn_run(engine->app.rknn_ctx, NULL);
    if (run_result == 0) {
        run_result = post_process(&engine->app, engine->app.output_mems,
                                  score_threshold, nms_threshold, &detections);
    }
    const std::chrono::steady_clock::time_point inference_end = std::chrono::steady_clock::now();
    if (run_result != 0) {
        set_error(error, error_size, "RKNN inference failed");
        return -3;
    }

    const float scale_x = (float)image.cols / (float)engine->app.model_width;
    const float scale_y = (float)image.rows / (float)engine->app.model_height;
    for (int index = 0; index < detections.count && result->detection_count < max_detections; ++index) {
        const object_detect_result *source = &detections.results[index];
        accelerator_detection_t *target = &result->detections[result->detection_count++];
        target->class_id = (uint32_t)source->cls_id;
        target->score = source->prop;
        target->left = (uint32_t)(source->box.left * scale_x);
        target->top = (uint32_t)(source->box.top * scale_y);
        target->right = (uint32_t)(source->box.right * scale_x);
        target->bottom = (uint32_t)(source->box.bottom * scale_y);
        std::snprintf(target->label, sizeof(target->label), "%s", coco_cls_to_name(source->cls_id));
    }

    const std::chrono::steady_clock::time_point total_end = std::chrono::steady_clock::now();
    result->decode_us = elapsed_us(total_start, decode_end);
    result->queue_us = elapsed_us(queue_start, queue_end);
    result->inference_us = elapsed_us(inference_start, inference_end);
    result->total_us = elapsed_us(total_start, total_end);
    return 0;
}

uint32_t accelerator_engine_queue_depth(const accelerator_engine_t *engine)
{
    return engine == NULL ? 0 : engine->waiting.load();
}

void accelerator_engine_destroy(accelerator_engine_t *engine)
{
    if (engine == NULL) {
        return;
    }

    deinit_post_process();
    rknn_context context = engine->app.rknn_ctx;
    for (uint32_t index = 0; index < engine->app.io_num.n_input; ++index) {
        if (engine->app.input_mems[index] != NULL) {
            rknn_destroy_mem(context, engine->app.input_mems[index]);
        }
    }
    for (uint32_t index = 0; index < engine->app.io_num.n_output; ++index) {
        if (engine->app.output_mems[index] != NULL) {
            rknn_destroy_mem(context, engine->app.output_mems[index]);
        }
    }
    if (context != 0) {
        rknn_destroy(context);
    }
    std::free(engine->app.input_attrs);
    std::free(engine->app.output_attrs);
    delete engine;
}