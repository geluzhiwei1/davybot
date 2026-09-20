# PyInstaller runtime hook — default text-mode open() to UTF-8.
#
# Runs before the entry script (dawei/cli/dawei.py) on every launch. On a
# zh-CN Windows host the process locale defaults to GBK (cp936), so any
# open() that omits an explicit encoding decodes UTF-8 files (templates,
# catalogs, configs, YAML) with GBK and crashes the sidecar — e.g. at import
# time via IPTemplateManager._load_index(). Dev hides this behind PYTHONUTF8=1,
# but the frozen sidecar neither honors PYTHONUTF8 reliably nor has it set by
# the Tauri launcher, so we force it here.
#
# This mirrors CPython's UTF-8 mode (PEP 540): only injects encoding="utf-8"
# when the caller did not specify one and the mode is not binary. It is a
# safety net — call sites should still pass encoding="utf-8" explicitly.
import builtins

_original_open = builtins.open


def _utf8_default_open(*args, **kwargs):
    # open(file, mode='r', buffering, encoding, ...) — encoding is the 4th
    # positional arg. Only inject when not provided (positionally or by keyword)
    # and the mode is text.
    if "encoding" not in kwargs and len(args) < 4:
        mode = args[1] if len(args) > 1 else kwargs.get("mode", "r")
        if "b" not in (mode or "r"):
            kwargs["encoding"] = "utf-8"
    return _original_open(*args, **kwargs)


builtins.open = _utf8_default_open
