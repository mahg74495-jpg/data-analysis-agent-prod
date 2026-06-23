"""Blueprint: system utilities — update disabled for air-gapped deployment."""
import logging
from pathlib import Path
from flask import Blueprint, jsonify

log = logging.getLogger(__name__)
bp = Blueprint("system", __name__)

@bp.post("/api/system/update")
def zip_update():
    """Update disabled — running in offline/intranet mode."""
    return jsonify({"ok": False, "message": "系统更新已禁用（离线模式）。如需更新请手动替换文件。"})

@bp.get("/api/instruction")
def get_instruction():
    """Return the raw Markdown of Instruction.md so the frontend can render it."""
    path = Path(__file__).parent.parent / "Instruction.md"
    if not path.exists():
        return jsonify({"ok": False, "error": "Instruction.md not found"}), 404
    try:
        return jsonify({"ok": True, "markdown": path.read_text(encoding="utf-8")})
    except OSError as exc:
        log.error("[instruction] read failed: %s", exc)
        return jsonify({"ok": False, "error": str(exc)}), 500
