from integrations.ds_proxy import app as dsapp


def test_usage_record_preserves_deepseek_cache_split():
    record = dsapp._usage_record("deepseek-v4-flash", False, {
        "prompt_tokens": 100,
        "completion_tokens": 20,
        "total_tokens": 120,
        "prompt_cache_hit_tokens": 30,
        "prompt_cache_miss_tokens": 70,
    })
    assert record["prompt_cache_hit_tokens"] == 30
    assert record["prompt_cache_miss_tokens"] == 70


def test_usage_record_derives_miss_from_openai_cached_tokens_detail():
    record = dsapp._usage_record("deepseek-v4-flash", True, {
        "prompt_tokens": 100,
        "completion_tokens": 20,
        "total_tokens": 120,
        "prompt_tokens_details": {"cached_tokens": 25},
    })
    assert record["prompt_cache_hit_tokens"] == 25
    assert record["prompt_cache_miss_tokens"] == 75
