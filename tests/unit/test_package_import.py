"""A packaging smoke test, not an RCA behavior test."""


def test_package_is_importable():
    import rca_ai

    assert rca_ai.__name__ == "rca_ai"
