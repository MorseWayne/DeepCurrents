# Event Intelligence Evaluation Fixtures

该目录用于存放 Event Intelligence Layer 的固定评估样本。

- `duplicate_pairs.json`: 明显重复或转载关系样本。
- `same_event_pairs.json`: 不同标题/不同表述但属于同一事件的样本。
- `top_event_relevance.json`: 用于评估排序结果的事件候选集合。
- `evaluation_result_sample.json`: `EvaluationRunner.run_all()` 的结构化输出样例。

这些文件由 `tests/evaluation/fixture_loader.py` 读取，并被后续 dedup / event / ranking 回归测试复用。
