#ifndef LUCKFOX_ACCELERATOR_ENGINE_H
#define LUCKFOX_ACCELERATOR_ENGINE_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define ACCELERATOR_MAX_DETECTIONS 128
#define ACCELERATOR_LABEL_SIZE 64

typedef struct accelerator_engine accelerator_engine_t;

typedef struct {
    const char *model_path;
    float default_score_threshold;
    float default_nms_threshold;
} accelerator_engine_config_t;

typedef struct {
    float score_threshold;
    float nms_threshold;
    uint32_t max_detections;
} accelerator_infer_options_t;

typedef struct {
    uint32_t class_id;
    char label[ACCELERATOR_LABEL_SIZE];
    float score;
    uint32_t left;
    uint32_t top;
    uint32_t right;
    uint32_t bottom;
} accelerator_detection_t;

typedef struct {
    uint32_t image_width;
    uint32_t image_height;
    uint32_t detection_count;
    accelerator_detection_t detections[ACCELERATOR_MAX_DETECTIONS];
    uint64_t queue_us;
    uint64_t decode_us;
    uint64_t inference_us;
    uint64_t total_us;
} accelerator_result_t;

int accelerator_engine_create(const accelerator_engine_config_t *config,
                              accelerator_engine_t **engine,
                              char *error,
                              size_t error_size);

int accelerator_engine_infer(accelerator_engine_t *engine,
                             const uint8_t *encoded_image,
                             size_t encoded_image_size,
                             const accelerator_infer_options_t *options,
                             accelerator_result_t *result,
                             char *error,
                             size_t error_size);

uint32_t accelerator_engine_queue_depth(const accelerator_engine_t *engine);
void accelerator_engine_destroy(accelerator_engine_t *engine);

#ifdef __cplusplus
}
#endif

#endif