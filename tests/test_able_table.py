from peak_assistant.able_assistant import able_table


async def test_able_table() -> None:
    # Test the basic functionality of able_table
    table = await able_table(
        hypothesis="Test Hypothesis",
        research_document="Test Research Document",
        local_context="Test Local Context",
        previous_run=[],
    )
    assert table is not None
    print(table)
