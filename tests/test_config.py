import pytest
from src.config.settings import CONFIG
from src.utils.logger import get_logger
import os

def test_config_loading():
    # 验证默认值或环境变量加载
    assert CONFIG.rss_timeout_ms == 15000
    # 验证是否正确解析了可选参数（如果有 .env 且包含 AI_MODEL）
    # 这里我们假设默认或环境中有值
    assert isinstance(CONFIG.ai_model, str)

def test_ai_default_values():
    assert CONFIG.ai_timeout_ms == 2000
    assert CONFIG.ai_max_context_tokens == 128000
    assert CONFIG.ai_symbol_search_timeout_ms == 3000

def test_logger_binding():
    logger = get_logger("test-engine")
    # 验证 logger 是否能正常工作（不抛出异常）
    logger.info("Test log message")
    assert True

if __name__ == "__main__":
    # 手动运行测试
    test_config_loading()
    test_logger_binding()
    print("Tests passed!")
