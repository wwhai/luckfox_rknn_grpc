#include "session_store.h"

#include <cassert>
#include <cstring>
#include <iostream>

int main()
{
    session_store_config_t config = {1, 60};
    session_store_t *store = NULL;
    assert(session_store_create(&config, &store) == 0);

    char first[SESSION_ID_SIZE];
    char second[SESSION_ID_SIZE];
    char model[SESSION_MODEL_SIZE];
    assert(session_store_open(store, "yolov5", first, sizeof(first)) == 0);
    assert(session_store_open(store, "yolov5", second, sizeof(second)) == -2);
    assert(session_store_count(store) == 1);
    assert(session_store_validate(store, first, model, sizeof(model)) == 0);
    assert(std::strcmp(model, "yolov5") == 0);
    assert(session_store_close(store, first) == 0);
    assert(session_store_close(store, first) == -2);
    assert(session_store_count(store) == 0);
    assert(session_store_open(store, "yolov5", second, sizeof(second)) == 0);

    session_store_destroy(store);
    std::cout << "session_store_test passed\n";
    return 0;
}