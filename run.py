"""消除车牌桌面应用启动脚本。"""

from app.config import AppPaths
from app.logging_setup import configure_logging, install_exception_hooks
from app.main import main


if __name__ == "__main__":
    log_path = configure_logging(AppPaths.default())
    install_exception_hooks(log_path)
    raise SystemExit(main())
