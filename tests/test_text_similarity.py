from src.utils.text_similarity import (
    dice_coefficient,
    generate_trigrams,
    jaccard_similarity,
)


def test_generate_trigrams_and_similarity_helpers():
    left = generate_trigrams("gold prices surge")
    right = generate_trigrams("gold prices rise")

    assert left
    assert right
    assert 0 < dice_coefficient(left, right) < 1
    assert jaccard_similarity({"gold", "prices"}, {"gold", "rise"}) == 1 / 3
