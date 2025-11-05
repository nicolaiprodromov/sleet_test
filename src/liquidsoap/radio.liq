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
  ignore(system("python3 /src/state-sync/publish-state.py #{state_file}"))
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

aac_stream = %ffmpeg(format="mpegts",
                     codec="aac",
                     channels=2,
                     ar=44100,
                     b="192k")

streams = [
  ("stream", aac_stream)
]

def segment_name(~position, ~extname, stream_name) =
  timestamp = int_of_float(time())
  duration = 6
  "#{stream_name}_#{duration}_#{timestamp}_#{position}.#{extname}"
end

streams_info = [
  ("stream", (200000, "mp4a.40.2", "ts"))
]

def on_file_change(~state, fname) =
  log_msg("File event: #{state} - #{fname}")
  
  # Only process completed .ts segments
  if state == "created" and string.match(pattern="\\.ts$", fname) then
    log_msg("New segment created: #{fname}")
    # The hls-to-ipfs.py service will automatically detect and upload this file
  elsif state == "created" and string.match(pattern="\\.m3u8$", fname) then
    log_msg("Playlist created: #{fname}")
  end
end

output.file.hls(
  playlist="live.m3u8",
  segment_duration=6.0,
  segments=10,
  segments_overhead=5,
  segment_name=segment_name,
  streams_info=streams_info,
  on_file_change=on_file_change,
  hls_dir,
  streams,
  music
)

log_msg("HLS output started with IPFS integration")
