from forge.report import END, START, table, with_block


def test_table():
    assert table(["a", "b"], [[1, 2]]) == "| a | b |\n|---|---|\n| 1 | 2 |"


def test_only_the_marked_block_is_replaced():
    readme = f"intro\n{START}\nold\n{END}\noutro\n"
    assert with_block(readme, "new") == f"intro\n{START}\nnew\n{END}\noutro\n"
