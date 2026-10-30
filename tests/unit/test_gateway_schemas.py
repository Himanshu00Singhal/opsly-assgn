from opsly.gateway.schemas import ChatRequest, ChatResponse


def test_chat_models() -> None:
    req = ChatRequest(message="What is FastAPI?")
    assert req.session_id == "default"
    resp = ChatResponse(session_id="s1", response="hi")
    assert resp.meta == {}
