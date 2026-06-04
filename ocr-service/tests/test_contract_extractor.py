"""Unit tests for the sales-contract price extraction strategies."""

from app.extraction.contract_extractor import _contract_price


def test_trec_cash_plus_loan():
    text = "Cash portion of Sales Price payable by Buyer  $30,000\n" \
           "Sum of all financing described below (Loan Amount)  $350,000"
    assert _contract_price(text) == "380000"


def test_explicit_sum_line():
    text = "Sales Price (Sum of A and B) ........ $412,500"
    assert _contract_price(text) == "412500"


def test_declaration_amount_on_next_line():
    # Georgia F201: label clause, value on the following line (price then concession).
    text = ("2. Purchase Price of Property to be Paid by Buyer. 3. Seller's Monetary "
            "Contribution toward Buyer's Costs at\n"
            "$ 263,000.00 Closing: $ 0.00\n"
            "4. Closing Date and Possession.")
    assert _contract_price(text) == "263000"


def test_blank_fillin_template_returns_none():
    # Michigan / Florida blank templates: the value is never in the text layer.
    text = ("6. Purchase Price: Buyer offers to buy the Property for the sum of $\n"
            "\n"
            "7. Seller Concessions, if any:")
    assert _contract_price(text) is None


def test_prose_mention_does_not_false_match():
    # Boilerplate prose must not be read as a price declaration.
    text = ("the earnest money shall be applied towards the purchase price of the Property\n"
            "$ 99,999.00 is an unrelated number in prose")
    assert _contract_price(text) is None
