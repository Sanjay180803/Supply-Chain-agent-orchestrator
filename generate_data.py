import random
from faker import Faker
from models import SessionLocal, init_db, Product, Supplier, SupplierContract, Inventory, Carrier

fake = Faker()

CATEGORIES = ["electronics", "textiles", "automotive_parts", "packaging", "raw_metals", "chemicals"]
REGIONS = ["North America", "Europe", "APAC", "LATAM", "MEA"]
WAREHOUSES = ["WH-EAST", "WH-WEST", "WH-CENTRAL", "WH-EU", "WH-APAC"]


def generate_products(n=100):
    products = []
    for _ in range(n):
        category = random.choice(CATEGORIES)
        products.append(
            Product(
                name=f"{fake.word().capitalize()} {category} unit",
                category=category,
                unit_cost=round(random.uniform(2, 500), 2),
            )
        )
    return products


def generate_suppliers(n=40):
    suppliers = []
    for _ in range(n):
        num_caps = random.randint(1, 3)
        caps = random.sample(CATEGORIES, num_caps)
        suppliers.append(
            Supplier(
                name=fake.company(),
                capabilities=",".join(caps),
                trust_score=round(random.uniform(0.5, 1.0), 2),
                country=fake.country(),
            )
        )
    return suppliers


def generate_contracts(suppliers, products):
    contracts = []
    for supplier in suppliers:
        supplier_caps = supplier.capabilities.split(",")
        eligible_products = [p for p in products if p.category in supplier_caps]
        chosen = random.sample(eligible_products, min(len(eligible_products), random.randint(3, 10)))
        for product in chosen:
            markup = random.uniform(0.9, 1.3)
            contracts.append(
                SupplierContract(
                    supplier_id=supplier.id,
                    product_id=product.id,
                    price=round(product.unit_cost * markup, 2),
                    lead_time_days=random.randint(2, 45),
                    terms=random.choice(["net-30", "net-60", "prepaid", "net-15"]),
                )
            )
    return contracts


def generate_inventory(products):
    inventory = []
    for product in products:
        for wh in random.sample(WAREHOUSES, random.randint(1, 3)):
            inventory.append(
                Inventory(
                    product_id=product.id,
                    warehouse_id=wh,
                    quantity=random.randint(0, 5000),
                )
            )
    return inventory


def generate_carriers(n=15):
    return [
        Carrier(
            name=fake.company() + " Logistics",
            region=random.choice(REGIONS),
            cost_per_kg=round(random.uniform(0.5, 8.0), 2),
            avg_transit_days=round(random.uniform(1, 20), 1),
        )
        for _ in range(n)
    ]


def main():
    init_db()
    db = SessionLocal()

    products = generate_products()
    db.add_all(products)
    db.commit()
    for p in products:
        db.refresh(p)

    suppliers = generate_suppliers()
    db.add_all(suppliers)
    db.commit()
    for s in suppliers:
        db.refresh(s)

    contracts = generate_contracts(suppliers, products)
    db.add_all(contracts)

    inventory = generate_inventory(products)
    db.add_all(inventory)

    carriers = generate_carriers()
    db.add_all(carriers)

    db.commit()
    db.close()

    print(f"Seeded {len(products)} products, {len(suppliers)} suppliers, "
          f"{len(contracts)} contracts, {len(inventory)} inventory rows, "
          f"{len(carriers)} carriers.")


if __name__ == "__main__":
    main()