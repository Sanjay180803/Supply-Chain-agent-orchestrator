from typing import Optional, List
from fastapi import FastAPI, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel

from models import get_db, Product, Supplier, SupplierContract, Inventory, Carrier

app = FastAPI(title="Supply Chain Dataset Service")


class ProductOut(BaseModel):
    id: int
    name: str
    category: str
    unit_cost: float

    class Config:
        from_attributes = True


class SupplierOut(BaseModel):
    id: int
    name: str
    capabilities: str
    trust_score: float
    country: str

    class Config:
        from_attributes = True


class InventoryOut(BaseModel):
    warehouse_id: str
    quantity: int

    class Config:
        from_attributes = True


class CarrierOut(BaseModel):
    id: int
    name: str
    region: str
    cost_per_kg: float
    avg_transit_days: float

    class Config:
        from_attributes = True


@app.get("/products", response_model=List[ProductOut])
def list_products(category: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(Product)
    if category:
        query = query.filter(Product.category == category)
    return query.all()


@app.get("/suppliers", response_model=List[SupplierOut])
def list_suppliers(capability: Optional[str] = Query(None), db: Session = Depends(get_db)):
    query = db.query(Supplier)
    if capability:
        query = query.filter(Supplier.capabilities.contains(capability))
    return query.all()


@app.get("/inventory/{product_id}", response_model=List[InventoryOut])
def get_inventory(product_id: int, db: Session = Depends(get_db)):
    rows = db.query(Inventory).filter(Inventory.product_id == product_id).all()
    if not rows:
        raise HTTPException(status_code=404, detail="No inventory found for this product")
    return rows


@app.get("/carriers", response_model=List[CarrierOut])
def list_carriers(region: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(Carrier)
    if region:
        query = query.filter(Carrier.region == region)
    return query.all()


@app.get("/suppliers/{supplier_id}/contracts")
def get_supplier_contracts(supplier_id: int, db: Session = Depends(get_db)):
    contracts = db.query(SupplierContract).filter(SupplierContract.supplier_id == supplier_id).all()
    return [
        {
            "product_id": c.product_id,
            "price": c.price,
            "lead_time_days": c.lead_time_days,
            "terms": c.terms,
        }
        for c in contracts
    ]


@app.get("/")
def root():
    return {"status": "ok", "service": "dataset_service"}