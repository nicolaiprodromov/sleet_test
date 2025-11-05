#!/usr/bin/liquidsoap

set("log.stdout", true)
set("log.level", 4)
set("init.allow_root", true)

node_id = getenv("NODE_ID")
ipfs_api = getenv("IPFS_API")
stream_topic = getenv("STREAM_TOPIC")

def log_msg(msg) =
  print("[#{node_id}] #{msg}")
end

log_msg("Starting P2P Radio Node")

state_file = "/state/current_position.json"
music_dir = "/music"
hls_dir = "/hls"

def read_state() =
  if file.exists(state_file) then
    content = file.contents(state_file)
    log_msg("Read state: #{content}")
    content
  else
    log_msg("No state file found")
    "{}"
  end
end

def write_state(position, track) =
  timestamp = int_of_float(time())
  state = "{\"position\": #{position}, \"track\": \"#{track}\", \"timestamp\": #{timestamp}, \"node_id\": \"#{node_id}\"}"
  file.write(data=state, state_file)
  ignore(system("python3 /scripts/publish-state.py #{state_file}"))
  ignore(log_msg("State updated: #{state}"))
end

playlist_file = "#{music_dir}/playlist.m3u"

music = playlist(
  mode="normal",
  reload_mode="watch",
  playlist_file
)

music = on_metadata(fun(m) -> (), music)

music = mksafe(music)

aac_lofi = %ffmpeg(format="mpegts",
                   codec="aac",
                   channels=2,
                   ar=44100,
                   b="64k")
aac_midfi = %ffmpeg(format="mpegts",
                    codec="aac",
                    channels=2,
                    ar=44100,
                    b="96k")
aac_hifi = %ffmpeg(format="mpegts",
                   codec="aac",
                   channels=2,
                   ar=44100,
                   b="192k")

streams = [
  ("lofi", aac_lofi),
  ("midfi", aac_midfi),
  ("hifi", aac_hifi)
]

def segment_name(~position, ~extname, stream_name) =
  timestamp = int_of_float(time())
  duration = 6
  "#{stream_name}_#{duration}_#{timestamp}_#{position}.#{extname}"
end

streams_info = [
  ("lofi", (70000, "mp4a.40.2", "ts")),
  ("midfi", (100000, "mp4a.40.2", "ts")),
  ("hifi", (200000, "mp4a.40.2", "ts"))
]

output.file.hls(
  playlist="live.m3u8",
  segment_duration=6.0,
  segments=10,
  segments_overhead=5,
  segment_name=segment_name,
  streams_info=streams_info,
  hls_dir,
  streams,
  music
)

log_msg("HLS output started")
