#include "shared_video.hpp"
#include <cstring>
#include <cerrno>
#include <random>
#ifdef _WIN32
#include <windows.h>
#include <sddl.h>
#else
#include <fcntl.h>
#include <semaphore.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>
#endif

struct SharedVideo::Impl {
    uint8_t *view = nullptr;
    std::string id;
    uint64_t sequence = 0;
#ifdef _WIN32
    HANDLE mapping = nullptr, mutex = nullptr;
#else
    int fd = -1;
    sem_t *semaphore = SEM_FAILED;
    std::string path, lock_path;
#endif
};
SharedVideo::SharedVideo() : state(new Impl) {}
SharedVideo::~SharedVideo() { close(); }
const std::string &SharedVideo::token() const { return state->id; }

bool SharedVideo::open()
{
    close();
    auto &s = *state;
    try {
        std::random_device random;
        constexpr char hex[] = "0123456789abcdef";
        for (unsigned i = 0; i < 32; ++i) s.id += hex[random() & 15];
    } catch (...) { return false; }
#ifdef _WIN32
    HANDLE token = nullptr;
    if (!OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, &token)) return false;
    DWORD size = 0;
    GetTokenInformation(token, TokenUser, nullptr, 0, &size);
    std::unique_ptr<uint8_t[]> user(new uint8_t[size]);
    bool ok = GetTokenInformation(token, TokenUser, user.get(), size, &size) != FALSE;
    CloseHandle(token);
    if (!ok) return false;
    LPWSTR sid = nullptr;
    if (!ConvertSidToStringSidW(reinterpret_cast<TOKEN_USER *>(user.get())->User.Sid, &sid)) return false;
    std::wstring acl = std::wstring(L"D:P(A;;GA;;;") + sid + L")";
    LocalFree(sid);
    PSECURITY_DESCRIPTOR descriptor = nullptr;
    if (!ConvertStringSecurityDescriptorToSecurityDescriptorW(acl.c_str(), SDDL_REVISION_1, &descriptor, nullptr)) return false;
    SECURITY_ATTRIBUTES attributes{sizeof(SECURITY_ATTRIBUTES), descriptor, FALSE};
    std::wstring name = L"Local\\StartLive.PkVideo." + std::wstring(s.id.begin(), s.id.end());
    s.mapping = CreateFileMappingW(INVALID_HANDLE_VALUE, &attributes, PAGE_READWRITE, 0, DWORD(capacity), name.c_str());
    bool exists = GetLastError() == ERROR_ALREADY_EXISTS;
    s.mutex = CreateMutexW(&attributes, FALSE, (name + L".lock").c_str());
    exists = exists || GetLastError() == ERROR_ALREADY_EXISTS;
    LocalFree(descriptor);
    if (!s.mapping || !s.mutex || exists) { close(); return false; }
    s.view = static_cast<uint8_t *>(MapViewOfFile(s.mapping, FILE_MAP_WRITE, 0, 0, capacity));
#else
    // Darwin POSIX names are limited to 31 bytes including the terminator.
    s.path = "/slpk-m-" + s.id.substr(0, 22);
    s.fd = shm_open(s.path.c_str(), O_CREAT | O_EXCL | O_RDWR, 0600);
    if (s.fd < 0) { s.path.clear(); return false; }
    s.lock_path = "/slpk-l-" + s.id.substr(0, 22);
    s.semaphore = sem_open(s.lock_path.c_str(), O_CREAT | O_EXCL, 0600, 1);
    if (s.semaphore == SEM_FAILED) { s.lock_path.clear(); close(); return false; }
    if (ftruncate(s.fd, capacity)) { close(); return false; }
    void *view = mmap(nullptr, capacity, PROT_READ | PROT_WRITE, MAP_SHARED, s.fd, 0);
    if (view != MAP_FAILED) s.view = static_cast<uint8_t *>(view);
#endif
    if (!s.view) { close(); return false; }
    std::memset(s.view, 0, 64);
    return true;
}

uint64_t SharedVideo::publish(const uint8_t *const planes[], const uint32_t strides[],
                             uint32_t width, uint32_t height, uint32_t format,
                             uint32_t colorspace, uint32_t range, uint64_t timestamp)
{
    auto &s = *state;
    if (!s.view || !width || !height || width > 3840 || height > 2160 ||
        (format != 1 && format != 2) || (colorspace != 1 && colorspace != 2) ||
        (range != 1 && range != 2)) return 0;
    const uint32_t row = width * (format == 1 ? 4 : 1);
    if (!planes[0] || strides[0] < row || (format == 2 &&
        ((width & 1) || (height & 1) || !planes[1] || strides[1] < width))) return 0;
#ifdef _WIN32
    DWORD locked = WaitForSingleObject(s.mutex, 0);
    if (locked != WAIT_OBJECT_0 && locked != WAIT_ABANDONED) return 0;
#else
    if (sem_trywait(s.semaphore)) return 0;
#endif
    uint8_t *out = s.view + 64;
    for (unsigned p = 0; p < (format == 2 ? 2u : 1u); ++p) {
        uint32_t rows = p ? height / 2 : height;
        if (strides[p] == row) {
            std::memcpy(out, planes[p], size_t(row) * rows);
            out += size_t(row) * rows;
        } else {
            for (uint32_t y = 0; y < rows; ++y, out += row)
                std::memcpy(out, planes[p] + size_t(y) * strides[p], row);
        }
    }
    // Fixed-width little-endian layout; never expose native structs/atomics.
    std::memset(s.view, 0, 64);
    std::memcpy(s.view, "SLVF", 4);
    auto put = [&](size_t offset, uint64_t n, unsigned count) {
        for (unsigned i = 0; i < count; ++i) s.view[offset + i] = uint8_t(n >> (8 * i));
    };
    put(4, 2, 4); put(8, ++s.sequence, 8); put(16, timestamp, 8);
    put(24, width, 4); put(28, height, 4); put(32, format, 4);
    put(36, colorspace, 4); put(40, range, 4); put(44, size_t(out - s.view - 64), 4);
#ifdef _WIN32
    ReleaseMutex(s.mutex);
#else
    sem_post(s.semaphore);
#endif
    return s.sequence;
}

void SharedVideo::close()
{
    auto &s = *state;
#ifdef _WIN32
    if (s.view) UnmapViewOfFile(s.view);
    if (s.mapping) CloseHandle(s.mapping);
    if (s.mutex) CloseHandle(s.mutex);
    s.mapping = s.mutex = nullptr;
#else
    if (s.view) munmap(s.view, capacity);
    if (s.fd >= 0) ::close(s.fd);
    if (!s.path.empty()) shm_unlink(s.path.c_str());
    if (s.semaphore != SEM_FAILED) sem_close(s.semaphore);
    if (!s.lock_path.empty()) sem_unlink(s.lock_path.c_str());
    s.semaphore = SEM_FAILED;
    s.lock_path.clear();
    s.fd = -1;
    s.path.clear();
#endif
    s.view = nullptr;
    s.id.clear();
    s.sequence = 0;
}
