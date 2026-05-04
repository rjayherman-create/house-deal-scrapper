from fastapi import FastAPI
from pydantic import BaseModel
from server.analysis import run_underwriting
from server.llm import generate_explanation

app = FastAPI()

class Listing(BaseModel):
    address: str
    city: str
    state: str
    zip_code: str
    asking_price: float

@app.post("/api/listings/analyze")
def analyze_listing(listing: Listing):
    underwriting = run_underwriting(listing.dict())
    explanation = generate_explanation(listing.dict(), underwriting)
    return {
        "underwriting": underwriting,
        "explanation": explanation
    }

@app.get("/")
def home():
    return {"status": "House Deal Scrapper Backend Running"}
@app.post("/api/listings/save")
def save_listing(listing: Listing):
    # TODO: save to SQLite or Postgres
    return {"status": "saved"}

@app.get("/api/listings/history")
def get_history():
    # TODO: fetch from DB
    return {"history": []}
