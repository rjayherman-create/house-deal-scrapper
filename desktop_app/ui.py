from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

try:
    from .client import analyze_market, fetch_saved_listings
except ImportError:
    from client import analyze_market, fetch_saved_listings


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()

        self.results = []
        layout = QVBoxLayout(self)

        input_row = QHBoxLayout()
        self.city_input = QLineEdit()
        self.city_input.setPlaceholderText("City")
        self.state_input = QLineEdit()
        self.state_input.setPlaceholderText("State")

        self.analyze_button = QPushButton("Analyze")
        self.analyze_button.clicked.connect(self.on_analyze_market)
        self.saved_button = QPushButton("Load Saved")
        self.saved_button.clicked.connect(self.on_load_saved)

        input_row.addWidget(QLabel("City:"))
        input_row.addWidget(self.city_input)
        input_row.addWidget(QLabel("State:"))
        input_row.addWidget(self.state_input)
        input_row.addWidget(self.analyze_button)
        input_row.addWidget(self.saved_button)
        layout.addLayout(input_row)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Address", "City", "State", "Price", "Score"])
        self.table.cellClicked.connect(self.on_row_selected)
        layout.addWidget(self.table)

        self.analysis_box = QTextEdit()
        self.analysis_box.setReadOnly(True)
        layout.addWidget(self.analysis_box)

    def set_busy(self, busy: bool, message: str):
        self.analyze_button.setEnabled(not busy)
        self.saved_button.setEnabled(not busy)
        if message:
            self.analysis_box.setText(message)

    def on_analyze_market(self):
        city = self.city_input.text().strip()
        state = self.state_input.text().strip()
        if not city or not state:
            self.analysis_box.setText("City and state are required.")
            return

        self.set_busy(True, "Running analysis...")
        self.worker = ListingsWorker("analyze", city, state)
        self.worker.finished.connect(self.on_results_loaded)
        self.worker.error.connect(self.on_error)
        self.worker.start()

    def on_load_saved(self):
        city = self.city_input.text().strip()
        state = self.state_input.text().strip()
        self.set_busy(True, "Loading saved listings...")
        self.worker = ListingsWorker("saved", city, state)
        self.worker.finished.connect(self.on_saved_loaded)
        self.worker.error.connect(self.on_error)
        self.worker.start()

    def on_results_loaded(self, results: list):
        self.set_busy(False, "")
        self.results = results
        self.populate_table()
        self.analysis_box.setText("Analysis complete. Select a row to view details.")

    def on_saved_loaded(self, saved_listings: list):
        self.set_busy(False, "")
        self.results = [
            {
                "listing": {
                    "address": listing.get("address", ""),
                    "city": listing.get("city", ""),
                    "state": listing.get("state", ""),
                    "price": listing.get("asking_price", 0),
                    "source": listing.get("source", ""),
                    "id": listing.get("id"),
                },
                "deal_scores": {"final_score": 0},
                "photo_analysis": {"notes": "Loaded from the database."},
                "system_ratings": {"notes": "No saved system ratings available."},
                "comp_analysis": {"notes": "No saved comp analysis available."},
                "questionnaire": {"sections": [], "checklist": {}},
            }
            for listing in saved_listings
        ]
        self.populate_table()
        self.analysis_box.setText("Saved listings loaded. Select a row to view details.")

    def on_error(self, message: str):
        self.set_busy(False, f"Error: {message}")

    def populate_table(self):
        self.table.setRowCount(len(self.results))
        for row, result in enumerate(self.results):
            listing = result.get("listing", {})
            score = result.get("deal_scores", {}).get("final_score", 0)

            self.table.setItem(row, 0, QTableWidgetItem(listing.get("address", "")))
            self.table.setItem(row, 1, QTableWidgetItem(listing.get("city", "")))
            self.table.setItem(row, 2, QTableWidgetItem(listing.get("state", "")))
            self.table.setItem(row, 3, QTableWidgetItem(f"${float(listing.get('price') or 0):,.0f}"))
            self.table.setItem(row, 4, QTableWidgetItem(f"{float(score):.2f}"))

    def on_row_selected(self, row: int, _column: int):
        result = self.results[row]
        listing = result.get("listing", {})
        deal_scores = result.get("deal_scores", {})
        photo_analysis = result.get("photo_analysis", {})
        system_ratings = result.get("system_ratings", {})
        comp_analysis = result.get("comp_analysis", {})

        text = (
            f"Listing ID: {listing.get('id', 'N/A')}\n"
            f"Address: {listing.get('address', '')}\n"
            f"Location: {listing.get('city', '')}, {listing.get('state', '')}\n"
            f"Price: ${float(listing.get('price') or 0):,.0f}\n"
            f"Source: {listing.get('source', '')}\n\n"
            f"Deal Score: {float(deal_scores.get('final_score') or 0):.2f}\n"
            f"Photo Notes: {photo_analysis.get('notes', '')}\n"
            f"System Notes: {system_ratings.get('notes', '')}\n"
            f"Comp Notes: {comp_analysis.get('notes', '')}"
        )
        self.analysis_box.setText(text)


class ListingsWorker(QThread):
    finished = Signal(list)
    error = Signal(str)

    def __init__(self, mode: str, city: str, state: str):
        super().__init__()
        self.mode = mode
        self.city = city
        self.state = state

    def run(self):
        try:
            if self.mode == "analyze":
                payload = analyze_market(self.city, self.state)
            else:
                payload = fetch_saved_listings(self.city, self.state)
            self.finished.emit(payload)
        except Exception as exc:
            self.error.emit(str(exc))
