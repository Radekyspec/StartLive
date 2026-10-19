#include "media_transport.hpp"
#include "shared_video.hpp"
#include <obs-module.h>
#include <obs-frontend-api.h>
#include <QAction>
#include <QPointer>
#include <algorithm>
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <cstring>
#include <deque>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

OBS_DECLARE_MODULE()
MODULE_EXPORT const char *obs_module_description(void)
{
    return "StartLive PK raw video/audio bridge (current user only)";
}

namespace {
constexpr size_t max_audio_bytes = 48000u * 4u / 5u; // 200 ms, independent of video
constexpr uint64_t video_interval_ns = 1000000000ull / STARTLIVE_PK_MAX_FPS;
struct Bridge;
Bridge *bridge_capture = nullptr;
QPointer<QAction> capture_action;
void raw_video(void *data, video_data *frame);
void raw_audio(void *data, size_t mix_idx, audio_data *audio);

void set_capture_text(QAction *action, bool capturing)
{
    action->setText(QString::fromUtf8(capturing ? u8"StartLive PK 采集：已开启"
                                              : u8"StartLive PK 采集：已关闭"));
}

void put32(std::vector<uint8_t> &v, uint32_t n)
{
    for (unsigned i = 0; i < 4; ++i) v.push_back(uint8_t(n >> (i * 8)));
}

std::vector<uint8_t> header(uint8_t kind, uint32_t size, uint64_t timestamp,
                            uint32_t width, uint32_t height, uint32_t frames)
{
    std::vector<uint8_t> v;
    v.reserve(36u + size);
    v.insert(v.end(), {'S', 'L', 'P', 'K', 2, kind, 0, 0});
    put32(v, size);
    put32(v, uint32_t(timestamp));
    put32(v, uint32_t(timestamp >> 32));
    put32(v, width);
    put32(v, height);
    put32(v, kind == 2 ? 48000 : 0);
    put32(v, frames);
    return v;
}

struct Bridge {
    obs_output_t *video_output = nullptr;
    audio_t *audio_source = nullptr;
    LocalMediaServer transport;
    SharedVideo video_memory;
    std::thread sender;
    std::mutex mutex;
    std::mutex capture_mutex;
    std::condition_variable ready;
    std::deque<std::vector<uint8_t>> audio_queue;
    std::vector<uint8_t> latest_video;
    size_t audio_bytes = 0;
    std::atomic<bool> active{false};
    std::atomic<bool> client_connected{false};
    uint32_t width = 0, height = 0;
    uint32_t pixel_format = 2, colorspace = 2, color_range = 1;
    uint64_t next_video_ns = 0;
    std::atomic<uint64_t> captured{0}, dropped{0}, sent{0};

    bool start();
    bool subscribe(bool audio, bool video);
    bool start_video_output();

    void unsubscribe()
    {
        // Disconnect waits for callbacks. Never hold a callback's locks here.
        if (video_output) {
            obs_output_stop(video_output);
            // OBS clears active after removing its raw callbacks. Wait even
            // if another observer temporarily holds an output reference.
            while (obs_output_active(video_output))
                std::this_thread::sleep_for(std::chrono::milliseconds(1));
            obs_output_release(video_output);
        }
        if (audio_source) audio_output_disconnect(audio_source, 0, raw_audio, this);
        video_output = nullptr;
        audio_source = nullptr;
    }

    void send_loop()
    {
        while (active && transport.accept_client()) {
            bool audio = true, video = true;
            if (!transport.capture_selection(audio, video)) {
                transport.disconnect_client();
                continue;
            }
            if (video) {
                std::lock_guard<std::mutex> lock(capture_mutex);
                if (!video_memory.open()) { transport.disconnect_client(); continue; }
            }
            if (video) {
                auto setup = header(3, 32, 0, 0, 0, 0);
                const auto &token = video_memory.token();
                setup.insert(setup.end(), token.begin(), token.end());
                if (!transport.write(setup.data(), setup.size())) {
                    video_memory.close();
                    transport.disconnect_client();
                    continue;
                }
            }
            // Do not replay frames collected before this client connected.
            {
                std::lock_guard<std::mutex> lock(mutex);
                audio_queue.clear();
                latest_video.clear();
                audio_bytes = 0;
                client_connected = true;
            }
            const bool subscribed = active && subscribe(audio, video);
            if (!subscribed) blog(LOG_ERROR, "[StartLive PK] Could not subscribe to requested capture streams");
            while (active && subscribed) {
                std::vector<uint8_t> packet;
                {
                    std::unique_lock<std::mutex> lock(mutex);
                    ready.wait_for(lock, std::chrono::milliseconds(250),
                        [this] { return !active || !audio_queue.empty() || !latest_video.empty(); });
                    if (!active) break;
                    if (audio_queue.empty() && latest_video.empty()) {
                        lock.unlock();
                        // Cancellation must free this single-client endpoint
                        // even if OBS has stopped delivering the selected stream.
                        if (!transport.client_alive()) break;
                        continue;
                    }
                    if (!audio_queue.empty()) {
                        packet = std::move(audio_queue.front());
                        audio_bytes -= packet.size();
                        audio_queue.pop_front();
                    } else {
                        packet.swap(latest_video);
                    }
                }
                if (!transport.write(packet.data(), packet.size())) break;
                if (packet[5] == 1) ++sent;
            }
            client_connected = false;
            unsubscribe();
            {
                std::lock_guard<std::mutex> lock(mutex);
                client_connected = false;
                audio_queue.clear();
                latest_video.clear();
                audio_bytes = 0;
            }
            transport.disconnect_client();
            {
                std::lock_guard<std::mutex> lock(capture_mutex);
                video_memory.close();
            }
        }
    }

    void enqueue(std::vector<uint8_t> packet)
    {
        std::lock_guard<std::mutex> lock(mutex);
        if (!active || !client_connected) return;
        // Never block the OBS render/audio thread on a slow client.
        if (packet[5] == 1) {
            if (!latest_video.empty()) ++dropped;
            latest_video = std::move(packet);
        } else {
            while (!audio_queue.empty() && audio_bytes + packet.size() > max_audio_bytes) {
                audio_bytes -= audio_queue.front().size();
                audio_queue.pop_front();
            }
            audio_bytes += packet.size();
            audio_queue.push_back(std::move(packet));
        }
        ready.notify_one();
    }

    void stop()
    {
        {
            std::lock_guard<std::mutex> lock(mutex);
            if (!active.exchange(false)) return;
            client_connected = false;
        }
        transport.interrupt();
        ready.notify_all();
        if (sender.joinable()) sender.join();
        transport.close();
        video_memory.close();
        audio_queue.clear();
        latest_video.clear();
        audio_bytes = 0;
        blog(LOG_INFO, "[StartLive PK] shared video: captured=%llu notifications=%llu dropped=%llu",
             (unsigned long long)captured.load(), (unsigned long long)sent.load(),
             (unsigned long long)dropped.load());
    }
};

bool Bridge::start()
{
    if (active) return true;
    if (!transport.open()) return false;
    captured = dropped = sent = 0;
    active = true;
    try { sender = std::thread(&Bridge::send_loop, this); }
    catch (...) {
        active = false;
        transport.close();
        return false;
    }
    return true;
}

bool Bridge::subscribe(bool capture_audio, bool capture_video)
{
    // Connect only requested raw streams: an audio-only client must not create
    // a video scaler, copy planes or depend on the OBS video format.
    if (capture_video) {
        video_output = obs_output_create(capture_audio ? "startlive_pk_output" :
                                         "startlive_pk_video_output", "StartLive PK", nullptr, nullptr);
        if (!video_output || !obs_output_start(video_output)) return false;
    } else if (capture_audio) {
        audio_convert_info audio{};
        audio.format = AUDIO_FORMAT_16BIT;
        audio.samples_per_sec = 48000;
        audio.speakers = SPEAKERS_STEREO;
        auto *source = obs_get_audio();
        if (!source || !audio_output_connect(source, 0, &audio, raw_audio, this)) return false;
        audio_source = source;
    }
    blog(LOG_INFO, "[StartLive PK] Capture selection: audio=%d video=%d", int(capture_audio), int(capture_video));
    return true;
}

bool Bridge::start_video_output()
{
    obs_video_info video{};
    if (!obs_get_video_info(&video) || video.output_width > 3840 || video.output_height > 2160 ||
        !obs_output_can_begin_data_capture(video_output, 0))
        return false;
    // Keep the OBS output resolution; cap video cadence using the app's limit.
    width = video.output_width;
    height = video.output_height;
    next_video_ns = 0;
    if (video.colorspace == VIDEO_CS_2100_PQ || video.colorspace == VIDEO_CS_2100_HLG) {
        blog(LOG_ERROR, "[StartLive PK] HDR requires explicit SDR tone mapping; choose an SDR OBS output");
        return false;
    }
    video_scale_info conversion{};
    pixel_format = (width % 2 || height % 2) ? 1 : 2;
    colorspace = video.colorspace == VIDEO_CS_601 ? 1 : 2;
    color_range = pixel_format == 1 || video.range == VIDEO_RANGE_FULL ? 2 : 1;
    conversion.format = pixel_format == 2 ? VIDEO_FORMAT_NV12 : VIDEO_FORMAT_BGRA;
    conversion.colorspace = colorspace == 1 ? VIDEO_CS_601 : VIDEO_CS_709;
    conversion.range = color_range == 2 ? VIDEO_RANGE_FULL : VIDEO_RANGE_PARTIAL;
    conversion.width = width;
    conversion.height = height;
    obs_output_set_video_conversion(video_output, &conversion);
    audio_convert_info audio{};
    audio.format = AUDIO_FORMAT_16BIT;
    audio.samples_per_sec = 48000;
    audio.speakers = SPEAKERS_STEREO;
    obs_output_set_audio_conversion(video_output, &audio);
    if (!obs_output_begin_data_capture(video_output, 0)) {
        // Software BGRA fallback stays on the same v2 shared-memory protocol.
        pixel_format = 1;
        color_range = 2;
        conversion.format = VIDEO_FORMAT_BGRA;
        conversion.range = VIDEO_RANGE_FULL;
        obs_output_set_video_conversion(video_output, &conversion);
        if (!obs_output_begin_data_capture(video_output, 0)) return false;
    }
    blog(LOG_INFO, "[StartLive PK] Capture %ux%u, at most %u fps, %s shared-memory v2",
         width, height, unsigned(STARTLIVE_PK_MAX_FPS), pixel_format == 2 ? "NV12" : "BGRA");
    return true;
}

void raw_video(void *data, video_data *frame)
{
    auto *bridge = static_cast<Bridge *>(data);
    if (!bridge->active || !bridge->client_connected || !frame->data[0]) return;
    if (frame->timestamp + 1000000ull < bridge->next_video_ns) return;
    if (!bridge->next_video_ns || frame->timestamp > bridge->next_video_ns + video_interval_ns)
        bridge->next_video_ns = frame->timestamp;
    bridge->next_video_ns += video_interval_ns;
    uint64_t sequence;
    {
        std::unique_lock<std::mutex> lock(bridge->capture_mutex, std::try_to_lock);
        if (!lock.owns_lock() || !bridge->client_connected) { ++bridge->dropped; return; }
        sequence = bridge->video_memory.publish(frame->data, frame->linesize,
            bridge->width, bridge->height, bridge->pixel_format, bridge->colorspace,
            bridge->color_range, frame->timestamp);
        if (!sequence) { ++bridge->dropped; return; }
        ++bridge->captured;
        auto packet = header(1, 8, 0, 0, 0, 0);
        put32(packet, uint32_t(sequence));
        put32(packet, uint32_t(sequence >> 32));
        bridge->enqueue(std::move(packet));
    }
}

void raw_audio(void *data, size_t, audio_data *audio)
{
    auto *bridge = static_cast<Bridge *>(data);
    if (!bridge->active || !bridge->client_connected || !audio->data[0] || !audio->frames || audio->frames > 4800) return;
    auto packet = header(2, audio->frames * 4, audio->timestamp, 0, 0, audio->frames);
    packet.insert(packet.end(), audio->data[0], audio->data[0] + audio->frames * 4);
    bridge->enqueue(std::move(packet));
}

void toggle_bridge(void *)
{
    if (!bridge_capture) return;
    if (bridge_capture->active) bridge_capture->stop();
    else if (!bridge_capture->start())
        blog(LOG_ERROR, "[StartLive PK] Could not start capture; check existing media connection");
    if (capture_action) set_capture_text(capture_action, bridge_capture->active);
}

void frontend_event(enum obs_frontend_event event, void *)
{
    if (event == OBS_FRONTEND_EVENT_EXIT && bridge_capture)
        bridge_capture->stop();
}
} // namespace

bool obs_module_load(void)
{
    obs_output_info info{};
    info.id = "startlive_pk_output";
    info.flags = OBS_OUTPUT_AV;
    info.get_name = [](void *) { return "StartLive PK raw media"; };
    // One local client owns the bridge. The output only owns its OBS capture
    // subscription; the menu owns the transport and Bridge lifetime.
    info.create = [](obs_data_t *, obs_output_t *) -> void * { return bridge_capture; };
    info.destroy = [](void *) {};
    info.start = [](void *data) { return static_cast<Bridge *>(data)->start_video_output(); };
    info.stop = [](void *data, uint64_t) {
        obs_output_end_data_capture(static_cast<Bridge *>(data)->video_output);
    };
    info.raw_video = raw_video;
    info.raw_audio = [](void *data, audio_data *audio) { raw_audio(data, 0, audio); };
    obs_register_output(&info);
    info.id = "startlive_pk_video_output";
    info.flags = OBS_OUTPUT_VIDEO;
    obs_register_output(&info);
    return true;
}

void obs_module_post_load(void)
{
    bridge_capture = new Bridge();
    capture_action = static_cast<QAction *>(obs_frontend_add_tools_menu_qaction(u8"StartLive PK 采集：已关闭"));
    if (capture_action) {
        capture_action->setEnabled(bridge_capture != nullptr);
        QObject::connect(capture_action, &QAction::triggered, capture_action, [] { toggle_bridge(nullptr); });
    }
    obs_frontend_add_event_callback(frontend_event, nullptr);
}

void obs_module_unload(void)
{
    obs_frontend_remove_event_callback(frontend_event, nullptr);
    if (bridge_capture) {
        bridge_capture->stop();
        delete bridge_capture;
        bridge_capture = nullptr;
    }
    delete capture_action.data();
}
