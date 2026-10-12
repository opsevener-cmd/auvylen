from aevyra_api.commercial.models import Product
from sqlalchemy import select


def test_renamed_brand_preserves_seed_and_order_identifiers(commerce):
    response = commerce.client.get("/api/v1/products")
    product = response.json()[0]
    assert product["name"] == "Auvylen Analysis"
    assert product["slug"] == "aevyra-test-analysis"
    with commerce.sessions() as session:
        stored = session.scalar(select(Product).where(Product.slug == product["slug"]))
        assert stored.name == "Aevyra Analysis"
        assert stored.price_amount == product["price_amount"] == 100
    order = commerce.client.post("/api/v1/orders", json={"product_slug": product["slug"]}).json()
    assert order["public_order_id"].startswith("av_")
    assert order["product"]["name"] == "Auvylen Analysis"
