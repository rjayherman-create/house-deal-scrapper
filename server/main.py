from fastapi import FastAPI, Depends
from pydantic import BaseModel
from sqlalchemy.future import select

from server.database import engine, get_db
from server.models import Base, ListingModel
from server.analysis import run_underwriting
from server.llm import generate_explanation

app = FastAPI()

class Listing(BaseModel):
    address: str
    city: str
    state: str
    zip_code: str
    asking_price: float


@app.on_event("startup")
async def on_startup():
    # Create tables on startup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@app.get("/")
def home():
    return {"status": "House Deal Scrapper Backend Running"}


@app.post("/api/listings/analyze")
def analyze_listing(listing: Listing):
    underwriting = run_underwriting(listing.dict())
    explanation = generate_explanation(listing.dict(), underwriting)
    return {
        "underwriting": underwriting,
        "explanation": explanation,
    }


@app.post("/api/listings/save")
async def save_listing(listing: Listing, db=Depends(get_db)):
    new_listing = ListingModel(**listing.dict())
    db.add(new_listing)
    await db.commit()
    await db.refresh(new_listing)
    return {"status": "saved", "id": new_listing.id}


@app.get("/api/listings/history")
async def get_history(db=Depends(get_db)):
    result = await db.execute(select(ListingModel))
    listings = result.scalars().all()
    return {
        "history": [
            {
                "id": l.id,
                "address": l.address,
                "city": l.city,
                "state": l.state,
                "zip_code": l.zip_code,
                "asking_price": l.asking_price,
            }
            for l in listings
        ]
    }

