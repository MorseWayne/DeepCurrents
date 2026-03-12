from loguru import logger
import sys
import os
from ..config.settings import CONFIG

def setup_logger():
    # 移除默认处理器
    logger.remove()

    # 配置标准错误输出
    if CONFIG.log_to_stderr:
        logger.add(
            sys.stderr,
            level=CONFIG.log_level,
            colorize=CONFIG.log_pretty,
            format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
        )

    # 配置本地文件落盘
    if CONFIG.log_to_file:
        log_dir = os.path.dirname(CONFIG.log_file_path)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir)
            
        logger.add(
            CONFIG.log_file_path,
            level=CONFIG.log_level,
            rotation="10 MB",
            retention="7 days",
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}"
        )

def get_logger(name: str):
    return logger.bind(name=name)

# 初始化全局日志配置
setup_logger()
