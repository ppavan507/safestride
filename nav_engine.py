import requests
import re

class NavEngine:
    def __init__(self, maps_key):
        self.key = maps_key
        self.url = "https://maps.googleapis.com/maps/api/directions/json"

    def get_step_directions(self, origin_lat_lon, destination):
        params = {
            'origin': origin_lat_lon, 
            'destination': destination, 
            'mode': 'walking', 
            'key': self.key
        }
        res = requests.get(self.url, params=params).json()
        if res['status'] == 'OK':
            instruction = res['routes'][0]['legs'][0]['steps'][0]['html_instructions']
            return re.sub('<[^<]+?>', '', instruction) # Strip HTML tags
        return "Route calculation in progress..."