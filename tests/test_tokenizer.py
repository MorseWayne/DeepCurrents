import pytest
from src.utils.tokenizer import tokenize, strip_source_attribution, contains_cjk

def test_contains_cjk():
    assert contains_cjk("Hello world") == False
    assert contains_cjk("你好，世界") == True
    assert contains_cjk("Mixed 你好") == True

def test_strip_source_attribution():
    assert strip_source_attribution("Market rally - Reuters") == "Market rally"
    assert strip_source_attribution("Breaking news | BBC News") == "Breaking news"
    assert strip_source_attribution("Normal - title - with - dashes") == "Normal - title - with"

def test_tokenize_english():
    text = "The global economy is facing new challenges according to reports."
    tokens = tokenize(text)
    assert "economy" in tokens
    assert "facing" in tokens
    assert "challenges" in tokens
    # 停用词不应存在
    assert "the" not in tokens
    assert "is" not in tokens
    assert "according" not in tokens

def test_tokenize_chinese():
    text = "全球经济面临新的挑战。"
    tokens = tokenize(text)
    assert "全球" in tokens
    assert "经济" in tokens
    assert "面临" in tokens
    assert "挑战" in tokens
    # 停用词
    assert "的" not in tokens

if __name__ == "__main__":
    pytest.main([__file__])
