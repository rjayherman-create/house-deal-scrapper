from fastapi import FastAPI
from pydantic import BaseModel
from analysis import run_underwriting
from llm import generate_explanation

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
