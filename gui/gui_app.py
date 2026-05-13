import os
import sys

import requests
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


API_BASE_URL = os.getenv("HOUSE_DEAL_SCRAPER_API_URL", "http://127.0.0.1:8000").rstrip("/")
ANALYZE_URL = f"{API_BASE_URL}/analyze"
LISTINGS_URL = f"{API_BASE_URL}/listings"


def build_saved_result(listing: dict) -> dict:
    price = float(listing.get("asking_price") or 0)
    return {
        "listing": {
            "id": listing.get("id"),
            "address": listing.get("address", ""),
            "city": listing.get("city", ""),
            "state": listing.get("state", ""),
            "zip_code": listing.get("zip_code", ""),
            "price": price,
            "source": listing.get("source") or "database",
        },
        "photo_analysis": {
            "category": "saved",
            "distress_evidence": False,
            "notes": "Loaded from the database. Run Analyze for a fresh market analysis.",
        },
        "system_ratings": {
            "kitchen_score": 0.0,
            "furnace_score": 0.0,
            "water_heater_score": 0.0,
            "notes": "No saved system ratings available.",
        },
        "comp_analysis": {
            "comp_score": 0.0,
            "photo_age_multiplier": 1.0,
            "notes": "No saved comp analysis available.",
        },
        "deal_scores": {
            "final_score": 0.0,
        },
        "questionnaire": {
            "sections": [],
            "checklist": {},
        },
    }


class AnalysisWorker(QThread):
    finished = Signal(list)
    error = Signal(str)

    def __init__(self, city: str, state: str, include_photos: bool):
        super().__init__()
        self.city = city
        self.state = state
        self.include_photos = include_photos

    def run(self):
        try:
            response = requests.get(
                ANALYZE_URL,
                params={
                    "city": self.city,
                    "state": self.state,
                    "include_photos": str(self.include_photos).lower(),
                },
                timeout=60,
            )
            response.raise_for_status()
            payload = response.json()
            if isinstance(payload, dict) and payload.get("error"):
                self.error.emit(payload.get("message", "Unknown error"))
                return
            self.finished.emit(payload)
        except Exception as exc:
            self.error.emit(str(exc))


class SavedListingsWorker(QThread):
    finished = Signal(list)
    error = Signal(str)

    def __init__(self, city: str, state: str):
        super().__init__()
        self.city = city
        self.state = state

    def run(self):
        try:
            params = {}
            if self.city:
                params["city"] = self.city
            if self.state:
                params["state"] = self.state

            response = requests.get(LISTINGS_URL, params=params, timeout=30)
            response.raise_for_status()
            payload = response.json()
            self.finished.emit(payload.get("listings", []))
        except Exception as exc:
            self.error.emit(str(exc))


class DealScraperGUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("House Deal Scraper")
        self.setMinimumWidth(1100)
        self.setMinimumHeight(700)
        self.results = []

        main_layout = QVBoxLayout()

        search_layout = QHBoxLayout()
        self.city_input = QLineEdit()
        self.city_input.setPlaceholderText("City")
        self.state_input = QLineEdit()
        self.state_input.setPlaceholderText("State (e.g., OH)")
        self.photo_checkbox = QCheckBox("Include Photos")

        self.search_button = QPushButton("Analyze")
        self.search_button.clicked.connect(self.start_analysis)
        self.saved_button = QPushButton("Load Saved")
        self.saved_button.clicked.connect(self.load_saved_listings)

        search_layout.addWidget(QLabel("API"))
        search_layout.addWidget(QLabel(API_BASE_URL))
        search_layout.addWidget(self.city_input)
        search_layout.addWidget(self.state_input)
        search_layout.addWidget(self.photo_checkbox)
        search_layout.addWidget(self.search_button)
        search_layout.addWidget(self.saved_button)

        self.tabs = QTabWidget()

        self.listings_table = QTableWidget()
        self.listings_table.setColumnCount(4)
        self.listings_table.setHorizontalHeaderLabels(["Address", "Price", "Score", "Source"])
        self.listings_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.listings_table.cellClicked.connect(self.load_listing_details)
        self.tabs.addTab(self.listings_table, "Listings")

        self.details_text = QTextEdit()
        self.details_text.setReadOnly(True)
        self.tabs.addTab(self.details_text, "Details")

        self.questionnaire_text = QTextEdit()
        self.questionnaire_text.setReadOnly(True)
        self.tabs.addTab(self.questionnaire_text, "Questionnaire")

        self.checklist_text = QTextEdit()
        self.checklist_text.setReadOnly(True)
        self.tabs.addTab(self.checklist_text, "Checklist")

        main_layout.addLayout(search_layout)
        main_layout.addWidget(self.tabs)
        self.setLayout(main_layout)

    def set_busy(self, busy: bool, message: str) -> None:
        self.search_button.setEnabled(not busy)
        self.saved_button.setEnabled(not busy)
        if message:
            self.details_text.setText(message)

    def start_analysis(self):
        city = self.city_input.text().strip()
        state = self.state_input.text().strip()

        if not city or not state:
            self.details_text.setText("City and state are required.")
            return

        self.set_busy(True, "Analyzing and saving listings...")
        include_photos = self.photo_checkbox.isChecked()
        self.worker = AnalysisWorker(city, state, include_photos)
        self.worker.finished.connect(self.display_results)
        self.worker.error.connect(self.display_error)
        self.worker.start()

    def load_saved_listings(self):
        city = self.city_input.text().strip()
        state = self.state_input.text().strip()

        self.set_busy(True, "Loading saved listings...")
        self.saved_worker = SavedListingsWorker(city, state)
        self.saved_worker.finished.connect(self.display_saved_results)
        self.saved_worker.error.connect(self.display_error)
        self.saved_worker.start()

    def display_saved_results(self, listings: list):
        self.display_results([build_saved_result(listing) for listing in listings])

    def display_results(self, results: list):
        self.set_busy(False, "")
        self.results = results
        self.listings_table.setRowCount(len(results))

        if not results:
            self.details_text.setText("No listings found.")
            self.questionnaire_text.clear()
            self.checklist_text.clear()
            return

        for index, result in enumerate(results):
            listing = result.get("listing", {})
            deal = result.get("deal_scores", {})
            price = listing.get("price") or 0
            score = float(deal.get("final_score") or 0.0)

            self.listings_table.setItem(index, 0, QTableWidgetItem(listing.get("address", "")))
            self.listings_table.setItem(index, 1, QTableWidgetItem(f"${price:,.0f}"))
            self.listings_table.setItem(index, 2, QTableWidgetItem(f"{score:.2f}"))
            self.listings_table.setItem(index, 3, QTableWidgetItem(listing.get("source", "")))

        self.details_text.setText("Select a listing to view details.")
        self.questionnaire_text.clear()
        self.checklist_text.clear()
        self.tabs.setCurrentIndex(0)

    def load_listing_details(self, row: int, _column: int):
        result = self.results[row]
        listing = result.get("listing", {})
        photo = result.get("photo_analysis", {})
        systems = result.get("system_ratings", {})
        comp = result.get("comp_analysis", {})
        deal = result.get("deal_scores", {})
        questionnaire = result.get("questionnaire", {})

        details = [
            f"{listing.get('address', '')} — {listing.get('city', '')}, {listing.get('state', '')}",
            f"Listing ID: {listing.get('id', 'N/A')}",
            f"Price: ${float(listing.get('price') or 0):,.0f}",
            f"Source: {listing.get('source', '')}",
            "",
            "--- Photo Analysis ---",
            f"Age Category: {photo.get('category', 'unknown')}",
            f"Distress Evidence: {photo.get('distress_evidence', False)}",
            f"Notes: {photo.get('notes', '')}",
            "",
            "--- System Ratings ---",
            f"Kitchen Score: {systems.get('kitchen_score', 0)}",
            f"Furnace Score: {systems.get('furnace_score', 0)}",
            f"Water Heater Score: {systems.get('water_heater_score', 0)}",
            f"Notes: {systems.get('notes', '')}",
            "",
            "--- Comp Analysis ---",
            f"Comp Score: {comp.get('comp_score', 0)}",
            f"Photo Multiplier: {comp.get('photo_age_multiplier', 0)}",
            f"Notes: {comp.get('notes', '')}",
            "",
            "--- Deal Score ---",
            f"Final Score: {deal.get('final_score', 0)}",
        ]
        self.details_text.setText("\n".join(details))

        sections = questionnaire.get("sections", [])
        if sections:
            qtext = []
            for section in sections:
                qtext.append(f"[{section.get('title', '')}]")
                for question in section.get("questions", []):
                    qtext.append(f" - {question}")
                qtext.append("")
            self.questionnaire_text.setText("\n".join(qtext).strip())
        else:
            self.questionnaire_text.setText("No questionnaire saved for this listing.")

        checklist = questionnaire.get("checklist", {})
        if checklist:
            ctext = []
            for category, items in checklist.items():
                ctext.append(f"{category.upper()}:")
                for item in items:
                    ctext.append(f" - {item}")
                ctext.append("")
            self.checklist_text.setText("\n".join(ctext).strip())
        else:
            self.checklist_text.setText("No checklist saved for this listing.")

        self.tabs.setCurrentIndex(1)

    def display_error(self, message: str):
        self.set_busy(False, f"Error: {message}")


def run_gui():
    app = QApplication(sys.argv)
    window = DealScraperGUI()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run_gui()
