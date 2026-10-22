"""📝 Text and specialised domains — Text models: AA Intelligence and every AA evaluation / domain index (medical, legal, engineering, finance…),
Arena text boards, Design Arena web/UI/3D/game/dataviz/SVG and agents, BridgeBench, video understanding (Video-MME-v2,
LLM Stats video boards)."""
LABEL = ("Texte et spécialités", "Text and specialised domains")
ICON = "📝"
# source kind -> parts to read (None = the whole source)
SOURCES = {"aa": None, "aa_eval": None, "bridgebench": None, "video_evals": None,
           "arena": {"text", "text_french", "text_coding", "text_creative", "webdev", "image_to_webdev", "vision", "document",
                     "search", "agent"},
           "da": {"allcategories", "website", "uicomponent", "gamedev", "dataviz", "3d", "svg", "agents"}}
