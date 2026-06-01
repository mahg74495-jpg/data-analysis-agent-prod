"""Blueprint: system utilities — update disabled for air-gapped deployment."""
import logging
from flask import Blueprint, jsonify

log = logging.getLogger(__name__)
bp = Blueprint("system", __name__)

@bp.post("/api/system/update")
def zip_update():
    """Update disabled — running in offline/intranet mode."""
    return jsonify({"ok": False, "message": "系统更新已禁用（离线模式）。如需更新请手动替换文件。"})

@bp.get("/api/instruction")
def get_instruction():
    return jsonify({"ok": True, "message": "离线部署模式"})
