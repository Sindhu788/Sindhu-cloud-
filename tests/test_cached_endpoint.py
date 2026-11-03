from sindhu_web import cache


def test_cached_endpoint_serves_cached_value_and_separates_query_parameters():
    cache.clear_all()
    calls = []

    @cache.cached_endpoint("t_endpoint", 60)
    def handler(base_id=None):
        calls.append(base_id)
        return {"base": base_id, "n": len(calls)}

    first = handler(base_id=None)
    again = handler(base_id=None)
    other = handler(base_id="x")
    assert first == again and calls == [None, "x"]
    assert other["base"] == "x"
    cache.clear_all()
