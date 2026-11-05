"""/scan log clear : le voyant ScanLog s'éteint, et le reste après un redémarrage (config)."""
from types import SimpleNamespace

from uexinfo.cli.commands import scan


def test_scan_log_clear_marks_log_seen(tmp_path, monkeypatch):
    log = tmp_path / "app.log"
    log.write_text("scan\n", encoding="utf-8")
    saved = []
    monkeypatch.setattr("uexinfo.config.settings.save", lambda cfg: saved.append(cfg))
    ctx = SimpleNamespace(cfg={"scan": {"sc_log_path": str(log)}}, log_last_mtime=0.0)
    scan.cmd_scan(["log", "clear"], ctx)
    assert ctx.log_last_mtime == log.stat().st_mtime
    assert saved and saved[-1]["scan"]["log_seen_mtime"] == log.stat().st_mtime
