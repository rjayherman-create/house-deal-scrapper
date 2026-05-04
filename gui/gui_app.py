import sys
import requests
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QCheckBox, QTabWidget,
    QTextEdit, QTableWidget, QTableWidgetItem, QHeaderView
)
from PySide6.QtCore import Qt, QThread, Signal


API_URL = "https://house-deal-scrapper-production.up.railway.app/analyze"


# ---------------------------------------------------------
# Worker Thread
# ---------------------------------------------------------

class AnalysisWorker(QThread):
    finished = Signal(list)
    error = Signal(str)

    def __init__(self, city, state, include_photos):
        super().__init__()
        self.city = city
        self.state = state
        self.include_photos = include_photos

    def run(self):
        try:
            params = {
                "city": self.city,
                "state": self.state,
                "include_photos": str(self.include_photos).lower()
            }
            response = requests.get(API_URL, params=params, timeout=60)

            if response.status_code != 200:
                self.error.emit(f"HTTP {response.status_code}: {response.text}")
                return

            data = response.json()

            if isinstance(data, dict) and data.get("error"):
                self.error.emit(data.get("message", "Unknown error"))
                return

            self.finished.emit(data)

        except Exception as e:
            self.error.emit(str(e))


# ---------------------------------------------------------
# Main GUI
# ---------------------------------------------------------

class DealScraperGUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("House Deal Scraper")
        self.setMinimumWidth(1100)
        self.setMinimumHeight(700)

        main_layout = QVBoxLayout()

        # -----------------------------
        # Search Bar
        # -----------------------------
        search_layout = QHBoxLayout()
        self.city_input = QLineEdit()
        self.city_input.setPlaceholderText("City")
        self.state_input = QLineEdit()
        self.state_input.setPlaceholderText("State (e.g., OH)")
        self.photo_checkbox = QCheckBox("Include Photos")

        self.search_button = QPushButton("Analyze")
        self.search_button.clicked.connect(self.start_analysis)

        search_layout.addWidget(self.city_input)
        search_layout.addWidget(self.state_input)
        search_layout.addWidget(self.photo_checkbox)
        search_layout.addWidget(self.search_button)

        # -----------------------------
        # Tabs
        # -----------------------------
        self.tabs = QTabWidget()

        # Listings tab
        self.listings_table = QTableWidget()
        self.listings_table.setColumnCount(4)
        self.listings_table.setHorizontalHeaderLabels(["Address", "Price", "Score", "Source"])
        self.listings_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.listings_table.cellClicked.connect(self.load_listing_details)

        self.tabs.addTab(self.listings_table, "Listings")

        # Details tab
        self.details_text = QTextEdit()
        self.details_text.setReadOnly(True)
        self.tabs.addTab(self.details_text, "Details")

        # Questionnaire tab
        self.questionnaire_text = QTextEdit()
        self.questionnaire_text.setReadOnly(True)
        self.tabs.addTab(self.questionnaire_text, "Questionnaire")

        # Checklist tab
        self.checklist_text = QTextEdit()
        self.checklist_text.setReadOnly(True)
        self.tabs.addTab(self.checklist_text, "Checklist")

        # Add to layout
        main_layout.addLayout(search_layout)
        main_layout.addWidget(self.tabs)
        self.setLayout(main_layout)

        # Storage for results
        self.results = []

    # -----------------------------------------------------
    # Start analysis
    # -----------------------------------------------------
    def start_analysis(self):
        city = self.city_input.text().strip()
        state = self.state_input.text().strip()

        if not city or not state:
            self.details_text.setText("City and State are required.")
            return

        self.search_button.setEnabled(False)
        self.details_text.setText("Analyzing...")

        include_photos = self.photo_checkbox.isChecked()

        self.worker = AnalysisWorker(city, state, include_photos)
        self.worker.finished.connect(self.display_results)
        self.worker.error.connect(self.display_error)
        self.worker.start()

    # -----------------------------------------------------
    # Display results in table
    # -----------------------------------------------------
    def display_results(self, results):
        self.search_button.setEnabled(True)
        self.results = results

        self.listings_table.setRowCount(len(results))

        for i, r in enumerate(results):
            listing = r["listing"]
            deal = r["deal_scores"]

            self.listings_table.setItem(i, 0, QTableWidgetItem(listing["address"]))
            self.listings_table.setItem(i, 1, QTableWidgetItem(str(listing["price"])))
            self.listings_table.setItem(i, 2, QTableWidgetItem(f"{deal['final_score']:.2f}"))
            self.listings_table.setItem(i, 3, QTableWidgetItem(listing["source"]))

        self.tabs.setCurrentIndex(0)

    # -----------------------------------------------------
    # Load details when clicking a listing
    # -----------------------------------------------------
    def load_listing_details(self, row, col):
        r = self.results[row]

        listing = r["listing"]
        photo = r["photo_analysis"]
        systems = r["system_ratings"]
        comp = r["comp_analysis"]
        deal = r["deal_scores"]
        questionnaire = r["questionnaire"]

        # DETAILS TAB
        details = ""
        details += f"{listing['address']} — {listing['city']}, {listing['state']}\n"
        details += f"Price: ${listing['price']}\n"
        details += f"Source: {listing['source']}\n\n"

        details += "--- Photo Analysis ---\n"
        details += f"Age Category: {photo['category']}\n"
        details += f"Distress Evidence: {photo['distress_evidence']}\n"
        details += f"Notes: {photo['notes']}\n\n"

        details += "--- System Ratings ---\n"
        details += f"Kitchen Score: {systems['kitchen_score']}\n"
        details += f"Furnace Score: {systems['furnace_score']}\n"
        details += f"Water Heater Score: {systems['water_heater_score']}\n"
        details += f"Notes: {systems['notes']}\n\n"

        details += "--- Comp Analysis ---\n"
        details += f"Comp Score: {comp['comp_score']}\n"
        details += f"Photo Multiplier: {comp['photo_age_multiplier']}\n\n"

        details += "--- Deal Score ---\n"
        details += f"Final Score: {deal['final_score']}\n\n"

        self.details_text.setText(details)

        # QUESTIONNAIRE TAB
        qtext = ""
        for section in questionnaire["sections"]:
            qtext += f"\n[{section['title']}]\n"
            for q in section["questions"]:
                qtext += f" - {q}\n"
        self.questionnaire_text.setText(qtext)

        # CHECKLIST TAB
        ctext = ""
        for cat, items in questionnaire["checklist"].items():
            ctext += f"\n{cat.upper()}:\n"
            for item in items:
                ctext += f" - {item}\n"
        self.checklist_text.setText(ctext)

        self.tabs.setCurrentIndex(1)

    # -----------------------------------------------------
    # Display error
    # -----------------------------------------------------
    def display_error(self, message):
        self.search_button.setEnabled(True)
        self.details_text.setText(f"Error: {message}")


# ---------------------------------------------------------
# App Entry
# ---------------------------------------------------------

def run_gui():
    app = QApplication(sys.argv)
    window = DealScraperGUI()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run_gui()
