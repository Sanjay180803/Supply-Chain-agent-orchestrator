from sqlalchemy import (
    Column, Integer, String, Float, ForeignKey, create_engine
)
from sqlalchemy.orm import relationship, declarative_base, sessionmaker

DATABASE_URL = "sqlite:///./data/supply_chain.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    category = Column(String, index=True)
    unit_cost = Column(Float, nullable=False)

    contracts = relationship("SupplierContract", back_populates="product")
    inventory = relationship("Inventory", back_populates="product")


class Supplier(Base):
    __tablename__ = "suppliers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    capabilities = Column(String, index=True)  # comma-separated categories
    trust_score = Column(Float, default=0.8)
    country = Column(String, index=True)

    contracts = relationship("SupplierContract", back_populates="supplier")


class SupplierContract(Base):
    __tablename__ = "supplier_contracts"

    id = Column(Integer, primary_key=True, index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    price = Column(Float, nullable=False)
    lead_time_days = Column(Integer, nullable=False)
    terms = Column(String, default="net-30")

    supplier = relationship("Supplier", back_populates="contracts")
    product = relationship("Product", back_populates="contracts")


class Inventory(Base):
    __tablename__ = "inventory"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    warehouse_id = Column(String, index=True)
    quantity = Column(Integer, default=0)

    product = relationship("Product", back_populates="inventory")


class Carrier(Base):
    __tablename__ = "carriers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    region = Column(String, index=True)
    cost_per_kg = Column(Float, nullable=False)
    avg_transit_days = Column(Float, nullable=False)


def init_db():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()