import requests

def test_karachi():
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": 24.8607,
        "longitude": 67.0011,
        "hourly": "temperature_2m",
        "timezone": "Asia/Karachi",
        "forecast_days": 1
    }
    response = requests.get(url, params=params)
    print(f"Status: {response.status_code}")
    print(response.json())

if __name__ == "__main__":
    test_karachi()
