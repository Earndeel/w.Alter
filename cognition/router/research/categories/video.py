"""🎬 Video — Video generation: AA text-to-video and image-to-video arenas, Arena text-to-video, image-to-video, video edit."""
LABEL = ("Vidéo", "Video")
ICON = "🎬"
# source kind -> parts to read (None = the whole source)
SOURCES = {"mm": {"video"}, "arena": {"text_to_video", "image_to_video", "video_edit"}}
