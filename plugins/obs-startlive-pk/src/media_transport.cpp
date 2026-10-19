#include "media_transport.hpp"
#include <algorithm>
#include <atomic>
#include <chrono>
#include <thread>
#include <string>
#include <vector>
#ifdef _WIN32
#include <windows.h>
#include <sddl.h>
#else
#include <cerrno>
#include <cstring>
#include <fcntl.h>
#include <poll.h>
#include <sys/file.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <unistd.h>
#endif

struct LocalMediaServer::Impl {
    std::atomic<bool> stopped{true};
    int buffer_size = 16 * 1024;
#ifdef _WIN32
    HANDLE pipe = INVALID_HANDLE_VALUE;
    HANDLE stop = nullptr;
    OVERLAPPED overlap{};
    bool finish(BOOL immediate, DWORD error)
    {
        if (immediate) return true;
        if (error != ERROR_IO_PENDING) return false;
        HANDLE events[] = {stop, overlap.hEvent};
        if (WaitForMultipleObjects(2, events, FALSE, INFINITE) != WAIT_OBJECT_0 + 1) {
            CancelIoEx(pipe, &overlap);
            WaitForSingleObject(overlap.hEvent, INFINITE);
            return false;
        }
        DWORD size = 0;
        return GetOverlappedResult(pipe, &overlap, &size, FALSE) != FALSE;
    }
#else
    int listener = -1, client = -1, lock = -1;
    std::string path;
    bool bound = false;
    bool wait(int fd, short events)
    {
        while (!stopped) {
            pollfd item{fd, events, 0};
            int result = poll(&item, 1, 50);
            if (result > 0) return (item.revents & events) != 0;
            if (result < 0 && errno != EINTR) return false;
        }
        return false;
    }
    static bool nonblocking(int fd)
    {
        return fcntl(fd, F_SETFD, FD_CLOEXEC) == 0 &&
            fcntl(fd, F_SETFL, O_NONBLOCK) == 0;
    }
#endif
};

LocalMediaServer::LocalMediaServer() : state(new Impl) {}
LocalMediaServer::~LocalMediaServer() { close(); }

bool LocalMediaServer::open(size_t buffer_size)
{
    close();
    auto &s = *state;
    s.buffer_size = int(std::max<size_t>(4096, std::min<size_t>(buffer_size, 1024 * 1024)));
#ifdef _WIN32
    HANDLE token = nullptr;
    if (!OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, &token)) return false;
    DWORD length = 0;
    GetTokenInformation(token, TokenUser, nullptr, 0, &length);
    std::vector<uint8_t> data(length);
    bool got_user = GetTokenInformation(token, TokenUser, data.data(), length, &length) != FALSE;
    CloseHandle(token);
    if (!got_user) return false;
    LPWSTR sid = nullptr;
    if (!ConvertSidToStringSidW(reinterpret_cast<TOKEN_USER *>(data.data())->User.Sid, &sid))
        return false;
    const std::wstring acl = std::wstring(L"D:P(A;;GA;;;") + sid + L")";
    LocalFree(sid);
    PSECURITY_DESCRIPTOR descriptor = nullptr;
    if (!ConvertStringSecurityDescriptorToSecurityDescriptorW(acl.c_str(), SDDL_REVISION_1,
                                                               &descriptor, nullptr))
        return false;
    SECURITY_ATTRIBUTES attributes{sizeof(SECURITY_ATTRIBUTES), descriptor, FALSE};
    constexpr auto pipe_name = L"\\\\.\\pipe\\StartLive.PkMedia.v2";
    s.pipe = CreateNamedPipeW(pipe_name,
        PIPE_ACCESS_DUPLEX | FILE_FLAG_OVERLAPPED | FILE_FLAG_FIRST_PIPE_INSTANCE,
        PIPE_TYPE_BYTE | PIPE_READMODE_BYTE | PIPE_WAIT | PIPE_REJECT_REMOTE_CLIENTS,
        1, DWORD(s.buffer_size), 4096, 0, &attributes);
    LocalFree(descriptor);
    s.stop = CreateEventW(nullptr, TRUE, FALSE, nullptr);
    s.overlap.hEvent = CreateEventW(nullptr, TRUE, FALSE, nullptr);
    if (s.pipe == INVALID_HANDLE_VALUE || !s.stop || !s.overlap.hEvent) { close(); return false; }
#else
    const auto directory = std::string("/tmp/startlive-pk-") + std::to_string(getuid());
    if (mkdir(directory.c_str(), 0700) != 0 && errno != EEXIST) return false;
    struct stat info{};
    if (lstat(directory.c_str(), &info) != 0 || !S_ISDIR(info.st_mode) ||
        info.st_uid != getuid() || (info.st_mode & 0077)) return false;
    // Hold a lock before removing a stale socket. A second OBS instance must
    // never unlink a live instance's endpoint.
    s.lock = ::open((directory + "/owner.lock").c_str(), O_CREAT | O_RDWR | O_CLOEXEC | O_NOFOLLOW, 0600);
    if (s.lock < 0) return false;
    if (flock(s.lock, LOCK_EX | LOCK_NB) != 0) { close(); return false; }
    s.path = directory + "/media-v2.sock";
    if (unlink(s.path.c_str()) != 0 && errno != ENOENT) { close(); return false; }
    s.listener = socket(AF_UNIX, SOCK_STREAM, 0);
    if (s.listener < 0 || !Impl::nonblocking(s.listener)) { close(); return false; }
    sockaddr_un address{};
    address.sun_family = AF_UNIX;
    if (s.path.size() >= sizeof(address.sun_path)) { close(); return false; }
    std::memcpy(address.sun_path, s.path.c_str(), s.path.size() + 1);
    if (bind(s.listener, reinterpret_cast<sockaddr *>(&address), sizeof(address)) != 0) { close(); return false; }
    s.bound = true;
    if (chmod(s.path.c_str(), 0600) != 0 || listen(s.listener, 1) != 0) { close(); return false; }
#endif
    s.stopped = false;
    return true;
}

bool LocalMediaServer::accept_client()
{
    auto &s = *state;
#ifdef _WIN32
    if (s.stopped) return false;
    ResetEvent(s.overlap.hEvent);
    BOOL connected = ConnectNamedPipe(s.pipe, &s.overlap);
    DWORD error = connected ? ERROR_SUCCESS : GetLastError();
    return error == ERROR_PIPE_CONNECTED || s.finish(connected, error);
#else
    while (s.wait(s.listener, POLLIN)) {
        s.client = accept(s.listener, nullptr, nullptr);
        if (s.client < 0) {
            if (errno == EAGAIN || errno == EINTR) continue;
            return false;
        }
        if (!Impl::nonblocking(s.client)) { disconnect_client(); return false; }
        // Video no longer occupies the socket. Bound queued PCM here as well
        // as in the application queue so slow readers do not replay seconds.
        if (setsockopt(s.client, SOL_SOCKET, SO_SNDBUF, &s.buffer_size, sizeof(s.buffer_size))) {
            disconnect_client(); return false;
        }
#ifdef SO_NOSIGPIPE
        int enabled = 1;
        if (setsockopt(s.client, SOL_SOCKET, SO_NOSIGPIPE, &enabled, sizeof(enabled)) != 0) {
            disconnect_client(); return false;
        }
#endif
        return true;
    }
    return false;
#endif
}

bool LocalMediaServer::capture_selection(bool &audio, bool &video)
{
    auto &s = *state;
    uint8_t request[8]{};
    size_t received = 0;
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(1);
    while (!s.stopped && received < sizeof(request)) {
        if (std::chrono::steady_clock::now() >= deadline) {
            if (received) return false; // Never default a partial request to AV.
            audio = video = true;
            return true;
        }
#ifdef _WIN32
        DWORD available = 0;
        if (!PeekNamedPipe(s.pipe, nullptr, 0, nullptr, &available, nullptr)) return false;
        if (!available) {
            std::this_thread::sleep_for(std::chrono::milliseconds(10));
            continue;
        }
        ResetEvent(s.overlap.hEvent);
        DWORD count = 0;
        BOOL ok = ReadFile(s.pipe, request + received,
                          DWORD(std::min<size_t>(available, sizeof(request) - received)),
                          &count, &s.overlap);
        if (!s.finish(ok, ok ? ERROR_SUCCESS : GetLastError()) ||
            !GetOverlappedResult(s.pipe, &s.overlap, &count, FALSE) || !count) return false;
#else
        auto count = recv(s.client, request + received, sizeof(request) - received, 0);
        if (count < 0 && (errno == EAGAIN || errno == EWOULDBLOCK || errno == EINTR)) {
            std::this_thread::sleep_for(std::chrono::milliseconds(10));
            continue;
        }
        if (count <= 0) return false;
#endif
        received += size_t(count);
    }
    if (s.stopped || received != sizeof(request) ||
        request[0] != 'S' || request[1] != 'L' || request[2] != 'P' || request[3] != 'C' ||
        request[4] != 1 || !request[5] || (request[5] & ~3) || request[6] || request[7])
        return false;
    audio = (request[5] & 1) != 0;
    video = (request[5] & 2) != 0;
    request[3] = 'A';
    return write(request, sizeof(request));
}

bool LocalMediaServer::client_alive()
{
    auto &s = *state;
    if (s.stopped) return false;
#ifdef _WIN32
    return PeekNamedPipe(s.pipe, nullptr, 0, nullptr, nullptr, nullptr) != FALSE;
#else
    uint8_t byte;
    auto count = recv(s.client, &byte, 1, MSG_PEEK);
    return count > 0 || (count < 0 &&
        (errno == EAGAIN || errno == EWOULDBLOCK || errno == EINTR));
#endif
}

bool LocalMediaServer::write(const uint8_t *data, size_t size)
{
    auto &s = *state;
    size_t offset = 0;
    while (!s.stopped && offset < size) {
#ifdef _WIN32
        ResetEvent(s.overlap.hEvent);
        DWORD sent = 0;
        BOOL ok = WriteFile(s.pipe, data + offset, DWORD(std::min<size_t>(size - offset, 1024 * 1024)),
                            &sent, &s.overlap);
        if (!s.finish(ok, ok ? ERROR_SUCCESS : GetLastError()) ||
            !GetOverlappedResult(s.pipe, &s.overlap, &sent, FALSE) || !sent) return false;
#else
        if (!s.wait(s.client, POLLOUT)) return false;
#ifdef MSG_NOSIGNAL
        constexpr int flags = MSG_NOSIGNAL;
#else
        constexpr int flags = 0;
#endif
        auto sent = send(s.client, data + offset, std::min<size_t>(size - offset, 1024 * 1024), flags);
        if (sent < 0 && (errno == EAGAIN || errno == EINTR)) continue;
        if (sent <= 0) return false;
#endif
        offset += size_t(sent);
    }
    return offset == size;
}

void LocalMediaServer::disconnect_client()
{
#ifdef _WIN32
    if (state->pipe != INVALID_HANDLE_VALUE) DisconnectNamedPipe(state->pipe);
#else
    if (state->client >= 0) ::close(state->client);
    state->client = -1;
#endif
}

void LocalMediaServer::interrupt()
{
    state->stopped = true;
#ifdef _WIN32
    if (state->stop) SetEvent(state->stop);
#endif
}

void LocalMediaServer::close()
{
    interrupt();
    disconnect_client();
#ifdef _WIN32
    if (state->pipe != INVALID_HANDLE_VALUE) CloseHandle(state->pipe);
    if (state->stop) CloseHandle(state->stop);
    if (state->overlap.hEvent) CloseHandle(state->overlap.hEvent);
    state->pipe = INVALID_HANDLE_VALUE;
    state->stop = state->overlap.hEvent = nullptr;
#else
    if (state->listener >= 0) ::close(state->listener);
    if (state->bound) unlink(state->path.c_str());
    if (state->lock >= 0) ::close(state->lock);
    state->listener = state->lock = -1;
    state->bound = false;
#endif
}
