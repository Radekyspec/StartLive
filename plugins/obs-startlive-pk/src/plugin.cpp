#include "media_transport.hpp"
#include "shared_video.hpp"
#include <obs-module.h>
#include <obs-frontend-api.h>
#include <QAction>
#include <QMetaObject>
#include <QPointer>
#include <algorithm>
#include <atomic>
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
obs_output_t *bridge_output = nullptr;
QPointer<QAction> capture_action;

void set_capture_text(QAction *action, bool capturing)
{
    action->setText(QString::fromUtf8(capturing ? u8"StartLive PK 采集：已开启"
                                              : u8"StartLive PK 采集：已关闭"));
}

void capture_started(void *data, calldata_t *)
{
    auto *action = static_cast<QAction *>(data);
    QMetaObject::invokeMethod(action, [action] { set_capture_text(action, true); }, Qt::QueuedConnection);
}

void capture_stopped(void *data, calldata_t *)
{
    auto *action = static_cast<QAction *>(data);
    QMetaObject::invokeMethod(action, [action] { set_capture_text(action, false); }, Qt::QueuedConnection);
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
    obs_output_t *output;
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

    explicit Bridge(obs_output_t *value) : output(value) {}

    void send_loop()
    {
        while (active && transport.accept_client()) {
            {
                std::lock_guard<std::mutex> lock(capture_mutex);
                if (!video_memory.open()) { transport.disconnect_client(); continue; }
            }
            auto setup = header(3, 32, 0, 0, 0, 0);
            const auto &token = video_memory.token();
            setup.insert(setup.end(), token.begin(), token.end());
            if (!transport.write(setup.data(), setup.size())) {
                std::lock_guard<std::mutex> lock(capture_mutex);
                video_memory.close();
                transport.disconnect_client();
                continue;
            }
            // Do not replay frames collected before this client connected.
            {
                std::lock_guard<std::mutex> lock(mutex);
                audio_queue.clear();
                latest_video.clear();
                audio_bytes = 0;
                client_connected = true;
            }
            while (active) {
                std::vector<uint8_t> packet;
                {
                    std::unique_lock<std::mutex> lock(mutex);
                    ready.wait(lock, [this] { return !active || !audio_queue.empty() || !latest_video.empty(); });
                    if (!active) break;
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
        if (!active.exchange(false)) return;
        client_connected = false;
        obs_output_end_data_capture(output);
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

bool start(void *data)
{
    auto *bridge = static_cast<Bridge *>(data);
    obs_video_info video{};
    if (!obs_get_video_info(&video) || video.output_width > 3840 || video.output_height > 2160 ||
        !obs_output_can_begin_data_capture(bridge->output, 0)) return false;
    // Keep the OBS output resolution; cap video cadence using the app's limit.
    bridge->width = video.output_width;
    bridge->height = video.output_height;
    bridge->next_video_ns = 0;
    bridge->captured = bridge->dropped = bridge->sent = 0;
    if (video.colorspace == VIDEO_CS_2100_PQ || video.colorspace == VIDEO_CS_2100_HLG) {
        blog(LOG_ERROR, "[StartLive PK] HDR requires explicit SDR tone mapping; choose an SDR OBS output");
        return false;
    }
    video_scale_info conversion{};
    bridge->pixel_format = (bridge->width % 2 || bridge->height % 2) ? 1 : 2;
    bridge->colorspace = video.colorspace == VIDEO_CS_601 ? 1 : 2;
    bridge->color_range = bridge->pixel_format == 1 || video.range == VIDEO_RANGE_FULL ? 2 : 1;
    conversion.format = bridge->pixel_format == 2 ? VIDEO_FORMAT_NV12 : VIDEO_FORMAT_BGRA;
    conversion.colorspace = bridge->colorspace == 1 ? VIDEO_CS_601 : VIDEO_CS_709;
    conversion.range = bridge->color_range == 2 ? VIDEO_RANGE_FULL : VIDEO_RANGE_PARTIAL;
    conversion.width = bridge->width;
    conversion.height = bridge->height;
    obs_output_set_video_conversion(bridge->output, &conversion);
    audio_convert_info audio{};
    audio.format = AUDIO_FORMAT_16BIT;
    audio.samples_per_sec = 48000;
    audio.speakers = SPEAKERS_STEREO;
    obs_output_set_audio_conversion(bridge->output, &audio);
    if (!bridge->transport.open()) return false;
    bridge->active = true;
    try { bridge->sender = std::thread(&Bridge::send_loop, bridge); }
    catch (...) {
        bridge->active = false;
        bridge->transport.close();
        bridge->video_memory.close();
        return false;
    }
    if (!obs_output_begin_data_capture(bridge->output, 0)) {
        // Software BGRA fallback stays on the same v2 shared-memory protocol.
        bridge->pixel_format = 1;
        bridge->color_range = 2;
        conversion.format = VIDEO_FORMAT_BGRA;
        conversion.range = VIDEO_RANGE_FULL;
        obs_output_set_video_conversion(bridge->output, &conversion);
        if (!obs_output_begin_data_capture(bridge->output, 0)) {
            bridge->stop();
            return false;
        }
    }
    blog(LOG_INFO, "[StartLive PK] Capture %ux%u, at most %u fps, %s shared-memory v2",
         bridge->width, bridge->height, unsigned(STARTLIVE_PK_MAX_FPS),
         bridge->pixel_format == 2 ? "NV12" : "BGRA");
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

void raw_audio(void *data, audio_data *audio)
{
    auto *bridge = static_cast<Bridge *>(data);
    if (!bridge->active || !bridge->client_connected || !audio->data[0] || !audio->frames || audio->frames > 4800) return;
    auto packet = header(2, audio->frames * 4, audio->timestamp, 0, 0, audio->frames);
    packet.insert(packet.end(), audio->data[0], audio->data[0] + audio->frames * 4);
    bridge->enqueue(std::move(packet));
}

void toggle_bridge(void *)
{
    if (!bridge_output) return;
    if (obs_output_active(bridge_output)) obs_output_stop(bridge_output);
    else if (!obs_output_start(bridge_output))
        blog(LOG_ERROR, "[StartLive PK] Could not start capture; check video size and existing media connection");
}

void frontend_event(enum obs_frontend_event event, void *)
{
    if (event == OBS_FRONTEND_EVENT_EXIT && bridge_output)
        obs_output_stop(bridge_output);
}
} // namespace

bool obs_module_load(void)
{
    obs_output_info info{};
    info.id = "startlive_pk_output";
    info.flags = OBS_OUTPUT_AV;
    info.get_name = [](void *) { return "StartLive PK raw media"; };
    info.create = [](obs_data_t *, obs_output_t *output) -> void * { return new Bridge(output); };
    info.destroy = [](void *data) { auto *b = static_cast<Bridge *>(data); b->stop(); delete b; };
    info.start = start;
    info.stop = [](void *data, uint64_t) { static_cast<Bridge *>(data)->stop(); };
    info.raw_video = raw_video;
    info.raw_audio = raw_audio;
    obs_register_output(&info);
    return true;
}

void obs_module_post_load(void)
{
    bridge_output = obs_output_create("startlive_pk_output", "StartLive PK", nullptr, nullptr);
    capture_action = static_cast<QAction *>(obs_frontend_add_tools_menu_qaction(u8"StartLive PK 采集：已关闭"));
    if (capture_action) {
        capture_action->setEnabled(bridge_output != nullptr);
        QObject::connect(capture_action, &QAction::triggered, capture_action, [] { toggle_bridge(nullptr); });
        if (bridge_output) {
            auto *output_signals = obs_output_get_signal_handler(bridge_output);
            signal_handler_connect(output_signals, "start", capture_started, capture_action.data());
            signal_handler_connect(output_signals, "deactivate", capture_stopped, capture_action.data());
        }
    }
    obs_frontend_add_event_callback(frontend_event, nullptr);
}

void obs_module_unload(void)
{
    obs_frontend_remove_event_callback(frontend_event, nullptr);
    if (bridge_output) {
        if (capture_action) {
            auto *output_signals = obs_output_get_signal_handler(bridge_output);
            signal_handler_disconnect(output_signals, "start", capture_started, capture_action.data());
            signal_handler_disconnect(output_signals, "deactivate", capture_stopped, capture_action.data());
        }
        obs_output_stop(bridge_output);
        obs_output_release(bridge_output);
        bridge_output = nullptr;
    }
    // Destroying the context also cancels queued status updates on unload.
    delete capture_action.data();
}
