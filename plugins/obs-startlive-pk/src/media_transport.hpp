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
    // Optional 8-byte SLPC selection: version 1, audio bit 0, video bit 1.
    // Legacy readers send nothing and retain audio + video after the timeout.
    bool capture_selection(bool &audio, bool &video);
    bool client_alive();
    bool write(const uint8_t *data, size_t size);
    void disconnect_client();
    void interrupt();
    void close(); // Call after the sending thread has joined.
private:
    struct Impl;
    std::unique_ptr<Impl> state;
};
