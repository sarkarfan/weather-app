import os
import sys

import requests
from PyQt5.QtCore import QObject, Qt, pyqtSignal, pyqtSlot
from PyQt5.QtWebChannel import QWebChannel
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

# Set OPENWEATHER_API_KEY in your environment; don't commit API keys.
API_KEY = os.getenv("OPENWEATHER_API_KEY", "")

MAP_HTML = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8" />
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="qrc:///qtwebchannel/qwebchannel.js"></script>
<style>html, body { height: 100%; margin: 0; } #map { height: 100%; width: 100%; }</style>
</head>
<body>
<div id="map"></div>
<script>
    var map = L.map('map', { minZoom: 2, maxBounds: [[-90, -Infinity], [90, Infinity]], maxBoundsViscosity: 1.0 }).setView([20, 0], 2);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { attribution: '&copy; OpenStreetMap contributors' }).addTo(map);
    var bridge;
    new QWebChannel(qt.webChannelTransport, function(channel) { bridge = channel.objects.bridge; });
    var marker;
    map.on('click', function(e) {
        var wrapped = e.latlng.wrap();
        if (marker) { map.removeLayer(marker); }
        marker = L.marker(wrapped).addTo(map);
        if (bridge) { bridge.coordinatesClicked(wrapped.lat, wrapped.lng); }
    });
</script>
</body>
</html>
"""


class MapBridge(QObject):
    """Receives click coordinates from the JavaScript map via QWebChannel."""

    coordinates_clicked = pyqtSignal(float, float)

    @pyqtSlot(float, float)
    def coordinatesClicked(self, lat, lon):
        self.coordinates_clicked.emit(lat, lon)


class WeatherApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Weather App")
        self.resize(950, 600)

        self.city_label = QLabel("Enter City:", self)
        self.city_input = QLineEdit(self)
        self.get_weather_button = QPushButton("Get Weather", self)
        self.city_name_label = QLabel(self)
        self.temperature_label = QLabel(self)
        self.emoji_label = QLabel(self)
        self.description_label = QLabel(self)
        self.minmax_label = QLabel(self)
        self.avg_label = QLabel(self)
        self.hint_label = QLabel("Or click a location on the map →", self)

        for label in (
            self.city_label, self.city_name_label, self.temperature_label,
            self.emoji_label, self.description_label, self.minmax_label,
            self.avg_label, self.hint_label,
        ):
            label.setAlignment(Qt.AlignCenter)
            label.setWordWrap(True)

        self.temperature_label.setStyleSheet("font-size: 28px; font-weight: bold;")
        self.emoji_label.setStyleSheet("font-size: 40px;")
        self.city_name_label.setStyleSheet("font-size: 16px; font-weight: bold;")

        info_layout = QVBoxLayout()
        for widget in (
            self.city_label, self.city_input, self.get_weather_button,
            self.hint_label,
        ):
            info_layout.addWidget(widget)
        info_layout.addSpacing(15)
        for widget in (
            self.city_name_label, self.emoji_label, self.temperature_label,
            self.description_label, self.minmax_label, self.avg_label,
        ):
            info_layout.addWidget(widget)
        info_layout.addStretch()

        info_panel = QWidget()
        info_panel.setLayout(info_layout)
        info_panel.setFixedWidth(260)

        self.map_view = QWebEngineView()
        self.map_view.setHtml(MAP_HTML)
        self.channel = QWebChannel()
        self.bridge = MapBridge()
        self.channel.registerObject("bridge", self.bridge)
        self.map_view.page().setWebChannel(self.channel)
        self.bridge.coordinates_clicked.connect(self.get_weather_by_coordinates)

        main_layout = QHBoxLayout()
        main_layout.addWidget(info_panel)
        main_layout.addWidget(self.map_view, stretch=1)
        self.setLayout(main_layout)

        self.get_weather_button.clicked.connect(self.get_weather_by_city)
        self.city_input.returnPressed.connect(self.get_weather_by_city)

    def get_weather_by_city(self):
        city = self.city_input.text().strip()
        if not city:
            self.display_error("Please enter a city name")
            return
        self.fetch_weather("https://api.openweathermap.org/data/2.5/weather", {"q": city})

    def get_weather_by_coordinates(self, lat, lon):
        self.fetch_weather(
            "https://api.openweathermap.org/data/2.5/weather",
            {"lat": lat, "lon": lon},
        )

    def fetch_weather(self, url, params):
        if not API_KEY:
            self.display_error("API key missing\nSet OPENWEATHER_API_KEY")
            return
        params.update({"appid": API_KEY, "units": "metric"})
        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            if data.get("cod") == 200:
                self.display_weather(data)
            else:
                self.display_error(f"Weather error\n{data.get('message', 'Request failed')}")
        except requests.exceptions.HTTPError:
            status_code = response.status_code
            messages = {
                400: "Bad request\nPlease check your input",
                401: "Unauthorized\nInvalid API key",
                403: "Forbidden\nAccess is denied",
                404: "Not found\nCity not found",
                500: "Internal server error\nPlease try again later",
                502: "Bad gateway\nInvalid response from server",
                503: "Service unavailable\nServer is down",
                504: "Gateway timeout\nNo response from server",
            }
            self.display_error(messages.get(status_code, f"HTTP error: {status_code}"))
        except requests.exceptions.ConnectionError:
            self.display_error("Connection error\nCheck your internet connection")
        except requests.exceptions.Timeout:
            self.display_error("Timeout error\nThe request timed out")
        except requests.exceptions.RequestException as error:
            self.display_error(f"Request error\n{error}")

    def display_error(self, message):
        self.city_name_label.clear()
        self.temperature_label.clear()
        self.emoji_label.clear()
        self.minmax_label.clear()
        self.avg_label.clear()
        self.description_label.setText(message)

    def display_weather(self, data):
        city_name = data.get("name", "")
        country = data.get("sys", {}).get("country", "")
        temperature_c = data["main"]["temp"]
        temp_min = data["main"]["temp_min"]
        temp_max = data["main"]["temp_max"]
        avg_temp = (temp_min + temp_max) / 2
        weather_id = data["weather"][0]["id"]
        description = data["weather"][0]["description"]

        self.city_name_label.setText(f"{city_name}, {country}" if country else city_name)
        self.temperature_label.setText(f"{temperature_c:.1f}°C")
        self.emoji_label.setText(self.get_weather_emoji(weather_id))
        self.description_label.setText(description.capitalize())
        self.minmax_label.setText(f"High: {temp_max:.1f}°C   Low: {temp_min:.1f}°C")
        self.avg_label.setText(f"Average: {avg_temp:.1f}°C")

    @staticmethod
    def get_weather_emoji(weather_id):
        if 200 <= weather_id <= 232:
            return "⛈️"
        if 300 <= weather_id <= 321:
            return "🌦️"
        if 500 <= weather_id <= 531:
            return "🌧️"
        if 600 <= weather_id <= 622:
            return "❄️"
        if 701 <= weather_id <= 741:
            return "🌫️"
        if weather_id == 762:
            return "🌋"
        if weather_id == 771:
            return "💨"
        if weather_id == 781:
            return "🌪️"
        if weather_id == 800:
            return "☀️"
        if 801 <= weather_id <= 804:
            return "☁️"
        return "❓"


if __name__ == "__main__":
    app = QApplication(sys.argv)
    weather_app = WeatherApp()
    weather_app.show()
    sys.exit(app.exec_())
