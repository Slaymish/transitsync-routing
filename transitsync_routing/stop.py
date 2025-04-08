class Stop:
    def __init__(self, stop_id, name, lat, lon):
        self.stop_id = stop_id
        self.name = name
        self.lat = float(lat)
        self.lon = float(lon)

    def __repr__(self):
        return f"Stop({self.stop_id}, {self.name}, {self.lat}, {self.lon})"
