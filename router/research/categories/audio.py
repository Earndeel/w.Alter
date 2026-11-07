"""🎧 Audio and music — Voice and music: AA text-to-speech, speech-to-speech, music (vocals, instrumental), AA speech-to-text."""
LABEL = ("Audio et musique", "Audio and music")
ICON = "🎧"
# source kind -> parts to read (None = the whole source)
SOURCES = {"mm": {"tts", "speech_to_speech", "music"}, "aa_stt": None}
