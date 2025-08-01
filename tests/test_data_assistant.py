# TODO: test this

# import pytest

# from data_assistant import identify_data_sources


# @pytest.mark.timeout(30)
# @pytest.mark.asyncio
# async def test_identify_data_sources() -> None:
#     """Test the identify_data_sources function."""
#     hypothesis = "PIFFLING PANGOLIN may be exfiltrating sensitive financial data using DNS tunneling."
#     research_document = (
#         "DNS tunneling is a technique used by threat actors to exfiltrate data."
#     )
#     local_context = (
#         "The organization has multiple DNS servers and monitors network traffic."
#     )

#     result = await identify_data_sources(
#         hypothesis=hypothesis,
#         research_document=research_document,
#         local_context=local_context,
#         able_info="Cheese",
#     )

#     assert isinstance(result, str)
#     assert "DNS servers" in result
#     assert "network traffic" in result
#     assert "exfiltration" in result
#     assert "PIFFLING PANGOLIN" in result
