import pytest
from funkbot.tool_protocol import CallAccumulator, declarations
from funkbot.tools import ToolError


def test_declarations_expose_only_the_two_typed_tools():
    items=declarations()
    assert [item['function']['name'] for item in items]==['web_fetch','write_note','create_followup']
    assert all(item['function']['parameters']['additionalProperties'] is False for item in items)


def test_fragmented_calls_reconstruct_in_index_order():
    stream=CallAccumulator()
    stream.feed({'tool_calls':[{'index':1,'id':'call_b','function':{'name':'write_','arguments':'{"filename":"x.txt",'}},{'index':0,'id':'call_a','function':{'name':'web_fetch','arguments':'{"url":"https://example.com"}'}}]})
    stream.feed({'tool_calls':[{'index':1,'function':{'name':'note','arguments':'"content":"hello"}'}}]})
    assert stream.finalize()==[{'id':'call_a','name':'web_fetch','arguments':{'url':'https://example.com'}},{'id':'call_b','name':'write_note','arguments':{'filename':'x.txt','content':'hello'}}]


@pytest.mark.parametrize('parts',[
    [{'index':0,'id':'a','function':{'name':'shell','arguments':'{}'}}],
    [{'index':7,'id':'a','function':{'name':'web_fetch','arguments':'{}'}}],
    [{'index':0,'id':'a','function':{'name':'web_fetch','arguments':'{'}}],
    [{'index':0,'id':'a','function':{'name':'web_fetch','arguments':'{"url":"x","shell":"bad"}'}}],
    [{'index':0,'id':'a','function':{'name':'web_fetch','arguments':'{"url":"x"}'}},{'index':1,'id':'a','function':{'name':'web_fetch','arguments':'{"url":"y"}'}}],
    [{'index':0,'id':'bad id','function':{'name':'web_fetch','arguments':'{"url":"x"}'}}],
    [{'index':0,'id':'a','function':{'name':'web_fetch','arguments':'x'*20001}}],
])
def test_invalid_streams_fail_closed(parts):
    stream=CallAccumulator()
    with pytest.raises(ToolError):
        stream.feed({'tool_calls':parts});stream.finalize()
