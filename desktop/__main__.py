"""python -m desktop"""
from desktop.app_code import prepare_runtime

prepare_runtime()
from desktop.launch import main

if __name__ == "__main__":
    raise SystemExit(main())
