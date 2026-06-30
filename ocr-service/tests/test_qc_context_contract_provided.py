from app.qc.context import QCContext


def test_context_accepts_contract_provided_flag():
    ctx = QCContext("t", contract_provided=True)

    assert ctx.contract_provided is True
    assert ctx.has_contract is True
