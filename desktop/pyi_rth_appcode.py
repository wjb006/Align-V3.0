"""PyInstaller runtime hook: choose app-code before the programme imports it."""


def _align_prepare_app_code() -> None:
    try:
        from desktop.app_code import prepare_runtime
        prepare_runtime()
    except Exception:
        return


_align_prepare_app_code()
