from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QTextEdit,
    QTableWidget, QTableWidgetItem
)
from PySide6.QtGui import QColor
import requests


API_URL = "https://house-deal-scrapper-production.up.railway.app"


def analyze_listing(data: dict):
    url = f"{API_URL}/api/listings/analyze"
    response = requests.post(url, json=data, timeout=20)
    response.raise_for_status()
    return response.json()


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()

        layout = QVBoxLayout(self)

        # -----------------------------------
        # TABLE SETUP (WITH SCORE COLUMN)
        # -----------------------------------
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "ID", "Address", "City", "State", "Price", "Score"
        ])
        layout.addWidget(self.table)

        # -----------------------------------
        # ANALYZE BUTTON + TEXT BOX
        # -----------------------------------
        self.analysis_btn = QPushButton("Analyze Deal")
        self.analysis_btn.clicked.connect(self.on_analyze)
        layout.addWidget(self.analysis_btn)

        self.analysis_box = QTextEdit()
        self.analysis_box.setReadOnly(True)
        layout.addWidget(self.analysis_box)

    # -----------------------------------
    # COLOR CODING FOR SCORE
    # -----------------------------------
    def color_for_score(self, score: int) -> QColor:
        if score >= 80:
            return QColor(0, 180, 0)      # green
        elif score >= 60:
            return QColor(200, 160, 0)    # yellow
        else:
            return QColor(200, 0, 0)      # red

    # -----------------------------------
    # ANALYZE BUTTON HANDLER
    # -----------------------------------
    def on_analyze(self):
        row = self.table.currentRow()
        if row < 0:
            return

        listing = {
            "address": self.table.item(row, 1).text(),
            "city": self.table.item(row, 2).text(),
            "state": self.table.item(row, 3).text(),
            "zip_code": "",
            "asking_price": float(self.table.item(row, 4).text()),
        }

        result = analyze_listing(listing)

        score = result["score"]
        underwriting = result["underwriting"]
        explanation = result["explanation"]

        # -----------------------------------
        # UPDATE SCORE COLUMN
        # -----------------------------------
        score_item = QTableWidgetItem(str(score))
        score_item.setForeground(self.color_for_score(score))
        self.table.setItem(row, 5, score_item)

        # -----------------------------------
        # UPDATE ANALYSIS PANEL
        # -----------------------------------
        text = (
            f"--- DEAL SCORE ---\n"
            f"{score}/100\n\n"
            f"--- UNDERWRITING ---\n"
            f"Cash Flow: {underwriting['cash_flow']}\n"
            f"Cap Rate: {underwriting['cap_rate']}\n"
            f"ROI: {underwriting['roi']}\n\n"
            f"--- AI EXPLANATION ---\n"
            f"{explanation}"
        )

        self.analysis_box.setText(text)
