from app._placeholder import scaffold_ready


def test_scaffold_ready() -> None:
    assert scaffold_ready() is True
