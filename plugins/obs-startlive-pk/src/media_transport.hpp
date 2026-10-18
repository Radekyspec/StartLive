#pragma once
#include <cstddef>
#include <cstdint>
#include <memory>

// Same-user, local-only stream. No OBS or Bilibili runtime dependency.
class LocalMediaServer {
public:
    LocalMediaServer();
    ~LocalMediaServer();
    bool open(size_t buffer_size = 16 * 1024);
    bool accept_client();
    bool write(const uint8_t *data, size_t size);
    void disconnect_client();
    void interrupt();
    void close(); // Call after the sending thread has joined.
private:
    struct Impl;
    std::unique_ptr<Impl> state;
};
