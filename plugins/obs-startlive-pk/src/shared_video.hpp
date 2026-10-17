#pragma once
#include <cstddef>
#include <cstdint>
#include <memory>
#include <string>

// One latest-frame mailbox. OS locks cover both header and pixels; producers
// never wait for readers. No borrowed OBS pointers survive the callback.
class SharedVideo {
public:
    static constexpr size_t capacity = 64u + 3840u * 2160u * 4u;
    SharedVideo();
    ~SharedVideo();
    bool open();
    void close();
    const std::string &token() const;
    uint64_t publish(const uint8_t *const planes[], const uint32_t strides[],
                     uint32_t width, uint32_t height, uint32_t format,
                     uint32_t colorspace, uint32_t range, uint64_t timestamp);
private:
    struct Impl;
    std::unique_ptr<Impl> state;
};
