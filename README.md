# TransitSync Routing 🚌

**TransitSync Routing** is a standalone Python package for planning public transit routes in Wellington, NZ using GTFS data from Metlink and geocoding from OpenStreetMap.

This repo is **open source** and focuses only on the route-planning logic. Calendar integrations, authentication, and full apps using this module are **kept private**.

---

## ✨ Features

- Geocode addresses using OpenStreetMap (with custom Wellington-specific normalization)
- Find nearest bus stops using Metlink GTFS
- Get live departure predictions
- Calculate walking or transit routes between calendar events
- Generate human-friendly summaries of trips

---

## 🚀 Installation

```bash
pip install git+https://github.com/Slaymish/transitsync-routing.git
```
