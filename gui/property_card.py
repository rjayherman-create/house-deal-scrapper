from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QHBoxLayout, QFrame
from PySide6.QtCore import Qt


class PropertyCard(QWidget):
    def __init__(self, listing, deal_score, on_click):
        super().__init__()

        self.listing = listing
        self.on_click = on_click

        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)

        # Card frame
        frame = QFrame()
        frame.setFrameShape(QFrame.StyledPanel)
        frame.setStyleSheet("""
            QFrame {
                background-color: #f5f5f5;
                border-radius: 8px;
                padding: 12px;
            }
        """)

        frame_layout = QVBoxLayout()

        # Address
        address = QLabel(f"<b>{listing['address']}</b>")
        address.setStyleSheet("font-size: 16px;")
        frame_layout.addWidget(address)

        # Price + Source
        info = QLabel(f"${listing['price']} — {listing['source']}")
        frame_layout.addWidget(info)

        # Deal Score (color-coded)
        score_label = QLabel(f"Deal Score: {deal_score:.2f}")
        color = "#4CAF50" if deal_score > 0.7 else "#FFC107" if deal_score > 0.4 else "#F44336"
        score_label.setStyleSheet(f"color: {color}; font-weight: bold;")
        frame_layout.addWidget(score_label)

        # Button
        btn = QPushButton("View Details")
        btn.clicked.connect(self.on_click)
        frame_layout.addWidget(btn)

        frame.setLayout(frame_layout)
        layout.addWidget(frame)
        self.setLayout(layout)
