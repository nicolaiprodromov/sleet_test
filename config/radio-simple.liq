#!/usr/bin/liquidsoap

settings.log.stdout.set(true)
settings.log.level.set(4)

music = playlist("/music/playlist.m3u")
music = mksafe(music)

output.file.hls(
  playlist="live.m3u8",
  "/hls",
  [("main", %ffmpeg(format="mpegts", %audio(codec="aac")))],
  music
)
