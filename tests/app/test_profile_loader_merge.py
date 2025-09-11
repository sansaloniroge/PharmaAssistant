from app.profile_loader import deep_merge

def test_deep_merge_nested():
    base = {"a": 1, "paths": {"x": 1, "y": 2}, "models": {"chat": "gpt"}}
    over = {"paths": {"y": 3, "z": 4}, "models": {"embedding": "emb"}}
    out = deep_merge(base, over)
    assert out["a"] == 1
    assert out["paths"] == {"x": 1, "y": 3, "z": 4}
    assert out["models"] == {"chat": "gpt", "embedding": "emb"}

def test_deep_merge_overwrites_scalars():
    base = {"top_k": 5, "temperature": 0.6}
    over = {"top_k": 7}
    out = deep_merge(base, over)
    assert out["top_k"] == 7
    assert out["temperature"] == 0.6
